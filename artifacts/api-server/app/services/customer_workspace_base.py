"""Shared scoped queries, durable events and bounded pagination."""
from uuid import UUID, uuid4
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from app.core.customer_security import now
from app.models.customer_workspace import CustomerResource, CustomerVehicle, CustomerBookingLink
from app.models.booking import Booking
from app.models.job import Job
from app.models.admin_operations import SourceRecord
from app.services.customer_otp_service import CustomerOTPService, fail


class CustomerWorkspaceBase(CustomerOTPService):
    def __init__(self, db, customer_id, request=None):
        super().__init__(db, request)
        self.customer_id = customer_id

    def query(self, kind):
        return select(CustomerResource).where(
            CustomerResource.customer_id == self.customer_id, CustomerResource.kind == kind)

    async def resource(self, identifier, kind):
        row = (await self.db.execute(self.query(kind).where(
            CustomerResource.id == identifier))).scalar_one_or_none()
        if not row:
            fail("RESOURCE_NOT_FOUND", 404)
        return row

    async def add(self, kind, payload, *, status="ACTIVE", parent_id=None, garage_id=None, key=None):
        row = CustomerResource(id=uuid4(), customer_id=self.customer_id, kind=kind,
                               status=status, payload=jsonable_encoder(payload), parent_id=parent_id,
                               garage_id=garage_id, dedupe_key=key, created_at=now())
        self.db.add(row)
        await self.db.flush()
        return row

    @staticmethod
    def row(row):
        return {"id": row.id, "status": row.status, "created_at": row.created_at,
                "updated_at": row.updated_at, **row.payload}

    async def page(self, query, page=1, page_size=20, render=None):
        total = (await self.db.execute(select(func.count()).select_from(
            query.order_by(None).subquery()))).scalar_one()
        items = (await self.db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all()
        if render:
            items = [await render(row) for row in items]
        else:
            items = [self.row(row) for row in items]
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    async def vehicle(self, identifier, *, archived=False):
        query = select(CustomerVehicle).where(CustomerVehicle.id == identifier,
                                               CustomerVehicle.customer_id == self.customer_id)
        if not archived:
            query = query.where(CustomerVehicle.archived_at.is_(None))
        row = (await self.db.execute(query)).scalar_one_or_none()
        if not row:
            fail("VEHICLE_NOT_FOUND", 404)
        return row

    async def booking(self, identifier):
        row = (await self.db.execute(select(Booking, CustomerBookingLink).join(
            CustomerBookingLink, CustomerBookingLink.booking_id == Booking.id).where(
                Booking.id == identifier, Booking.deleted_at.is_(None),
                CustomerBookingLink.customer_id == self.customer_id))).one_or_none()
        if not row:
            fail("RESOURCE_NOT_FOUND", 404)
        return row

    async def job(self, identifier):
        row = (await self.db.execute(select(Job).join(
            CustomerBookingLink, CustomerBookingLink.booking_id == Job.booking_id).where(
                Job.id == identifier, Job.deleted_at.is_(None),
                CustomerBookingLink.customer_id == self.customer_id))).scalar_one_or_none()
        if not row:
            fail("RESOURCE_NOT_FOUND", 404)
        return row

    async def source(self, identifier, kind):
        row = (await self.db.execute(select(SourceRecord).where(
            SourceRecord.id == identifier, SourceRecord.kind == kind,
            SourceRecord.customer_id == self.customer_id))).scalar_one_or_none()
        if not row:
            fail("RESOURCE_NOT_FOUND", 404)
        return row

    async def notify(self, category, title, reference_id, event_key):
        existing = (await self.db.execute(self.query("NOTIFICATION").where(
            CustomerResource.dedupe_key == event_key))).scalar_one_or_none()
        if not existing:
            await self.add("NOTIFICATION", {
                "category": category, "title": title, "reference_id": str(reference_id),
                "is_read": False, "occurred_at": now(),
            }, key=event_key)

    async def cursor_messages(self, parent, kind, cursor, limit):
        query = self.query(kind).where(CustomerResource.parent_id == parent.id)
        if cursor:
            marker = await self.resource(cursor, kind)
            if marker.parent_id != parent.id:
                fail("CURSOR_INVALID", 422)
            from sqlalchemy import tuple_
            query = query.where(tuple_(CustomerResource.created_at, CustomerResource.id) >
                                tuple_(marker.created_at, marker.id))
        rows = (await self.db.execute(query.order_by(CustomerResource.created_at, CustomerResource.id)
                                      .limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [self.row(row) for row in rows],
                "next_cursor": str(rows[-1].id) if has_more else None}
