from datetime import datetime, timezone
from decimal import Decimal

from app.core.exceptions import NotFoundException
from app.models.user import UserRole
from app.repositories.admin_monitoring_repository import AdminMonitoringRepository
from app.schemas.admin import AdminAuditResponse
from app.schemas.admin_monitoring import (
    AdminActivityEvent, AdminBookingDetail, AdminOwnerDetail, AdminOwnerSummary, AdminTimelineEvent,
)
from app.schemas.auth import UserResponse
from app.schemas.booking import BookingDetailResponse
from app.schemas.garage import GarageResponse
from app.schemas.response import PaginatedData
from app.services.admin_service import AdminService
from app.services.garage_service import _with_logo_url
from sqlalchemy import func, select
from app.models.admin_operations import SourceRecord
from app.models.garage import Garage
from app.core.admin_read_filters import apply_admin_filters


class AdminMonitoringService(AdminService):
    def __init__(self, session):
        super().__init__(session)
        self.repo = AdminMonitoringRepository(session)

    async def owners(self, filters, search, status, include_deleted, page, page_size, min_rating=None):
        query = self.repo.owners_query(filters, search, status, include_deleted)
        rating_query = select(Garage.user_id, func.avg(SourceRecord.payload["rating"].as_integer())).join(
            SourceRecord, SourceRecord.garage_id == Garage.id).where(
                SourceRecord.kind == "REVIEW", SourceRecord.status == "PUBLISHED", Garage.deleted_at.is_(None))
        rating_query = apply_admin_filters(rating_query, filters, SourceRecord.occurred_at).group_by(Garage.user_id)
        if min_rating is not None:
            rating_ids = rating_query.having(func.avg(SourceRecord.payload["rating"].as_integer()) >= min_rating).with_only_columns(Garage.user_id)
            query = query.where(self.repo.users_query().selected_columns.id.in_(rating_ids))
        owners, total = await self.repo.page(query, page, page_size)
        aggregates = await self.repo.owner_aggregates(owners, filters)
        ratings = dict((await self.session.execute(rating_query)).all())
        summaries = [self.owner_summary(owner, aggregates) for owner in owners]
        for summary in summaries:
            summary.average_rating = float(ratings[summary.id]) if summary.id in ratings else None
        return PaginatedData(
            items=summaries, total=total,
            page=page, page_size=page_size, pages=max(1, (total + page_size - 1) // page_size),
        )

    @staticmethod
    def owner_summary(owner, aggregates):
        grouped, bookings, jobs, amounts = aggregates
        garages = grouped.get(owner.id, [])
        previews = sorted(garages, key=lambda g: str(g.id))[:100]
        return AdminOwnerSummary(
            **UserResponse.model_validate(owner).model_dump(), display_name=owner.name,
            garage_ids=[g.id for g in previews], total_garages=len(garages),
            related_garages_truncated=len(garages) > 100,
            cities=sorted({g.city for g in previews if g.city}),
            bookings=bookings.get(owner.id, 0), jobs_created=jobs.get(owner.id, (0, 0))[0],
            completed_jobs=jobs.get(owner.id, (0, 0))[1],
            completed_job_amount_paise=int(Decimal(str(amounts.get(owner.id, 0))) * 100),
        )

    async def owner_detail(self, owner_id, filters, include_deleted=False):
        owner = await self.repo.get_user(owner_id, include_deleted)
        if not owner or owner.role != UserRole.GARAGE_OWNER.value:
            raise NotFoundException("Garage owner not found.")
        aggregates = await self.repo.owner_aggregates([owner], filters)
        rating_query = select(func.avg(SourceRecord.payload["rating"].as_integer())).select_from(
            SourceRecord).join(Garage, SourceRecord.garage_id == Garage.id).where(
                Garage.user_id == owner_id, SourceRecord.kind == "REVIEW", SourceRecord.status == "PUBLISHED",
                Garage.deleted_at.is_(None))
        rating = (await self.session.execute(apply_admin_filters(rating_query, filters, SourceRecord.occurred_at))).scalar_one()
        summary = self.owner_summary(owner, aggregates)
        summary.average_rating = float(rating) if rating is not None else None
        return AdminOwnerDetail(
            **summary.model_dump(),
            garages=[_with_logo_url(GarageResponse.model_validate(g)) for g in
                     sorted(aggregates[0].get(owner.id, []), key=lambda g: str(g.id))[:100]],
        )

    async def booking_detail(self, booking_id):
        booking = await self.repo.get_booking(booking_id)
        if not booking:
            raise NotFoundException("Booking not found.")
        jobs = await self.repo.booking_jobs(booking_id)
        history = (await self.session.execute(select(SourceRecord).where(
            SourceRecord.kind == "BOOKING_EVENT", SourceRecord.booking_id == booking_id,
        ).order_by(SourceRecord.occurred_at.desc(), SourceRecord.id).limit(101))).scalars().all()
        decision = next((event for event in history if event.status in ("ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED")), None)
        from app.services.admin_operations_service import record_row
        return AdminBookingDetail(
            **BookingDetailResponse.model_validate(booking).model_dump(),
            linked_job_ids=[j.id for j in jobs[:100]], linked_jobs_truncated=len(jobs) > 100,
            decision_actor=decision.payload.get("actor_id") if decision else None,
            decision_reason=decision.payload.get("reason") if decision else None,
            decision_timestamp=decision.occurred_at if decision else None,
            history=[record_row(event) for event in history[:100]], history_truncated=len(history) > 100,
            missing_history=[field for field, value in {
                "decision_actor": decision.payload.get("actor_id") if decision else None,
                "decision_reason": decision.payload.get("reason") if decision else None,
                "decision_timestamp": decision.occurred_at if decision else None,
            }.items() if value is None],
        )

    async def timeline(self, job_id, page, page_size):
        if not await self.repo.get_job(job_id):
            raise NotFoundException("Job not found.")
        return await self.page(self.repo.timeline_query(job_id), AdminTimelineEvent, page, page_size)

    async def exceptions(self, filters, group_by=None):
        if group_by is not None:
            from collections import Counter
            from zoneinfo import ZoneInfo
            from fastapi import HTTPException
            dimensions = group_by.split(",")
            if not dimensions or len(set(dimensions)) != len(dimensions) or set(dimensions) - {"owner", "garage", "reason", "city", "day"}:
                raise HTTPException(422, "GROUP_BY_INVALID")
            query = select(SourceRecord, Garage.user_id, Garage.city).join(Garage).where(
                SourceRecord.kind == "BOOKING_EVENT", SourceRecord.status.in_(["REJECTED", "CANCELLED", "EXPIRED"]),
                Garage.deleted_at.is_(None))
            events = (await self.session.execute(apply_admin_filters(
                query, filters, SourceRecord.occurred_at).order_by(SourceRecord.id).limit(10001))).all()
            if len(events) > 10000:
                raise HTTPException(413, "RESULT_TOO_LARGE")
            groups, reasons = Counter(), Counter()
            counts = Counter()
            for event, owner_id, city in events:
                reason = event.payload.get("reason") or "UNSPECIFIED"
                values = {"owner": str(owner_id), "garage": str(event.garage_id), "reason": reason,
                          "city": city, "day": event.occurred_at.astimezone(ZoneInfo(filters.timezone)).date().isoformat()}
                groups[tuple(values[dimension] for dimension in dimensions)] += 1
                reasons[reason] += 1
                counts[event.status] += 1
            return {"filters": filters.metadata(), "generated_at": datetime.now(timezone.utc),
                    "cohort": "booking.exception_event.occurred_at", "rejected": counts["REJECTED"],
                    "cancelled": counts["CANCELLED"], "expired": counts["EXPIRED"],
                    "reason_counts": dict(reasons), "breakdown": [
                        {**dict(zip(dimensions, key)), "count": count} for key, count in sorted(groups.items(), key=lambda item: str(item[0]))],
                    "breakdown_truncated": False, "unavailable_states": [], "reason_history_available": True,
                    "source_status": "RECORDED_EVENTS" if events else "NO_RECORDED_EVENTS"}
        rows = await self.repo.booking_exceptions(filters)
        total = sum(row[2] for row in rows)
        return {
            "filters": filters.metadata(), "generated_at": datetime.now(timezone.utc),
            "cohort": "booking.created_at", "rejected": total,
            "reason_counts": {"UNSPECIFIED": total},
            "breakdown": [{"owner_id": row[0], "city": row[1], "reason": "UNSPECIFIED", "count": row[2]} for row in rows[:100]],
            "breakdown_truncated": len(rows) > 100,
            "unavailable_states": ["CANCELLED", "EXPIRED"],
            "reason_history_available": False,
        }

    async def audit_detail(self, audit_id):
        audit = await self.repo.get_audit(audit_id)
        if not audit:
            raise NotFoundException("Audit record not found.")
        return AdminAuditResponse.model_validate(audit)

    async def activity(self, filters, page, page_size, **kwargs):
        query = self.repo.activity_query(filters, **kwargs)
        items, total = await self.repo.activity_page(query, page, page_size)
        return PaginatedData(
            items=[AdminActivityEvent.model_validate(item) for item in items], total=total,
            page=page, page_size=page_size, pages=max(1, (total + page_size - 1) // page_size),
        )

    async def recorded_types(self, filters, **kwargs):
        query = self.repo.activity_query(filters, **kwargs)
        return set((await self.session.execute(
            query.with_only_columns(query.selected_columns.event_type).order_by(None).distinct()
        )).scalars().all())

    async def funnel(self, booking_id, filters, page, page_size):
        booking = await self.repo.get_booking(booking_id)
        if not booking:
            raise NotFoundException("Booking not found.")
        jobs = await self.repo.booking_jobs(booking_id)
        events = await self.activity(filters, page, page_size, booking_id=booking_id)
        recorded = await self.recorded_types(filters, booking_id=booking_id)
        return {
            "booking_id": booking.id, "customer_id": booking.customer_id, "garage_id": booking.garage_id,
            "job_ids": [job.id for job in jobs[:100]], "linked_jobs_truncated": len(jobs) > 100,
            "events": events,
            "data_coverage": {
                "booking_decisions": bool(recorded & {"BOOKING_ACCEPTED", "BOOKING_REJECTED", "BOOKING_CANCELLED", "BOOKING_EXPIRED"}),
                "invoices": "INVOICE_ISSUED" in recorded,
                "payments": bool(recorded & {"PAYMENT_CAPTURED", "PAYMENT_FAILED"}),
                "reviews": "REVIEW_PUBLISHED" in recorded,
            },
        }
