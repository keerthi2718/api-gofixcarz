"""Scoped operational metrics: job.created_at cohort, never payment estimates."""
from dataclasses import replace
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import and_, func, select
from app.core.admin_policy import require_permission
from app.core.admin_read_filters import apply_admin_filters
from app.models.booking import Booking
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.services.admin_service import AdminService
from app.services.garage_service import _with_logo_url
from app.schemas.garage import GarageResponse


class AdminGarageManagement:
    def __init__(self, session):
        self.session = session
        self.admin = AdminService(session)

    def aggregate(self, filters, status=None):
        conditions = [Job.garage_id == Garage.id, Job.deleted_at.is_(None)]
        if filters.date_from:
            conditions.append(Job.created_at >= filters.boundary(filters.date_from))
        if filters.date_to:
            conditions.append(Job.created_at < filters.boundary(filters.date_to, exclusive_end=True))
        if status is not None:
            conditions.append(Job.status == status)
        query = select(
            Garage.id.label("garage_id"), Garage.name.label("garage_name"),
            Garage.operational_status, Garage.verification_status,
            func.count(Job.id).label("job_card_count"),
            *[func.count(Job.id).filter(Job.status == state).label(state.value.lower())
              for state in JobStatus],
        ).outerjoin(Job, and_(*conditions)).where(Garage.deleted_at.is_(None))
        return apply_admin_filters(query, filters).group_by(Garage.id)

    def row(self, row):
        data = dict(row._mapping)
        counts = {state.value: data.pop(state.value.lower()) for state in JobStatus}
        return {**data, "total_jobs": data["job_card_count"], "status_counts": counts,
                "completed_jobs": counts["COMPLETED"],
                "active_jobs": sum(v for k, v in counts.items() if k not in ("COMPLETED", "CANCELLED")),
                "completion_rate_percent": round(counts["COMPLETED"] * 100 / data["job_card_count"], 2)
                if data["job_card_count"] else 0}

    def metadata(self, filters, status):
        return {"filters": {**filters.metadata(), "status": status.value if status else None},
                "generated_at": datetime.now(timezone.utc),
                "metric_basis": "Non-deleted jobs grouped by garage, filtered by job.created_at and current job status. "
                                "Date endpoints are inclusive in the selected timezone. Garages without matching jobs have zero counts."}

    async def metrics(self, garage_id, filters, status=None):
        if filters.garage_id is not None and filters.garage_id != garage_id:
            raise HTTPException(422, "CONFLICTING_GARAGE_FILTER")
        filters = replace(filters, garage_id=garage_id)
        row = (await self.session.execute(self.aggregate(filters, status))).first()
        if not row:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        bookings = select(func.count(Booking.id)).join(Garage, Garage.id == Booking.garage_id).where(
            Garage.id == garage_id, Garage.deleted_at.is_(None), Booking.deleted_at.is_(None))
        bookings = apply_admin_filters(bookings, filters, Booking.created_at)
        return {**self.row(row), "booking_count": (await self.session.execute(bookings)).scalar_one(),
                "booking_count_basis": "booking.created_at date cohort; the job status filter does not apply to bookings",
                **self.metadata(filters, status)}

    async def report(self, filters, status, page, page_size):
        query = self.aggregate(filters, status)
        total = (await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        rows = (await self.session.execute(query.order_by(Garage.name, Garage.id).offset(
            (page - 1) * page_size).limit(page_size))).all()
        return {"items": [self.row(row) for row in rows], "total": total, "page": page,
                "page_size": page_size, "pages": max(1, (total + page_size - 1)//page_size),
                **self.metadata(filters, status)}

    async def patch(self, admin, garage_id, data):
        changes = data.model_dump(exclude={"reason", "expected_version"}, exclude_unset=True)
        if "verification_status" in changes:
            require_permission(self.session, "garages.verify", recent_mfa=True)
        if "operational_status" in changes:
            require_permission(self.session, "garages.status.write", recent_mfa=True)
        garage = (await self.session.execute(select(Garage).where(
            Garage.id == garage_id, Garage.deleted_at.is_(None),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not garage:
            raise HTTPException(404, "RESOURCE_NOT_FOUND")
        if garage.admin_version != data.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        before = {field: getattr(garage, field) for field in changes}
        for field, value in changes.items():
            setattr(garage, field, value)
        garage.admin_version += 1
        await self.session.flush()
        await self.session.refresh(garage)
        from fastapi.encoders import jsonable_encoder
        await self.admin.audit(admin.id, "garages.update", garage_id, jsonable_encoder({
            "before": before, "after": changes, "reason": data.reason, "version": garage.admin_version,
        }))
        return _with_logo_url(GarageResponse.model_validate(garage))
