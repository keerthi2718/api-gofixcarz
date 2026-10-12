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


class AdminMonitoringService(AdminService):
    def __init__(self, session):
        super().__init__(session)
        self.repo = AdminMonitoringRepository(session)

    async def owners(self, filters, search, status, include_deleted, page, page_size):
        query = self.repo.owners_query(filters, search, status, include_deleted)
        owners, total = await self.repo.page(query, page, page_size)
        aggregates = await self.repo.owner_aggregates(owners, filters)
        return PaginatedData(
            items=[self.owner_summary(owner, aggregates) for owner in owners], total=total,
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
        return AdminOwnerDetail(
            **self.owner_summary(owner, aggregates).model_dump(),
            garages=[_with_logo_url(GarageResponse.model_validate(g)) for g in
                     sorted(aggregates[0].get(owner.id, []), key=lambda g: str(g.id))[:100]],
        )

    async def booking_detail(self, booking_id):
        booking = await self.repo.get_booking(booking_id)
        if not booking:
            raise NotFoundException("Booking not found.")
        jobs = await self.repo.booking_jobs(booking_id)
        return AdminBookingDetail(
            **BookingDetailResponse.model_validate(booking).model_dump(),
            linked_job_ids=[j.id for j in jobs[:100]], linked_jobs_truncated=len(jobs) > 100,
            missing_history=["decision_actor", "decision_reason", "decision_timestamp"],
        )

    async def timeline(self, job_id, page, page_size):
        if not await self.repo.get_job(job_id):
            raise NotFoundException("Job not found.")
        return await self.page(self.repo.timeline_query(job_id), AdminTimelineEvent, page, page_size)

    async def exceptions(self, filters):
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

    async def funnel(self, booking_id, filters, page, page_size):
        booking = await self.repo.get_booking(booking_id)
        if not booking:
            raise NotFoundException("Booking not found.")
        jobs = await self.repo.booking_jobs(booking_id)
        events = await self.activity(filters, page, page_size, booking_id=booking_id)
        return {
            "booking_id": booking.id, "customer_id": booking.customer_id, "garage_id": booking.garage_id,
            "job_ids": [job.id for job in jobs[:100]], "linked_jobs_truncated": len(jobs) > 100,
            "events": events,
            "data_coverage": {"booking_decisions": False, "invoices": False, "payments": False, "reviews": False},
        }
