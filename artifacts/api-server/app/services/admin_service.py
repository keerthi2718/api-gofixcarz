import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_account import AdminAccount
from app.models.user import User, UserRole
from app.repositories.admin_repository import AdminRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.schemas.admin import (
    AdminAnalyticsResponse, AdminAuditResponse, AdminDashboardResponse, AdminGarageDetail,
    AdminTimeSeriesPoint, AdminUserDetail,
)
from app.schemas.auth import UserResponse
from app.schemas.booking import BookingResponse
from app.schemas.garage import GarageResponse
from app.schemas.job import JobDetailResponse, JobResponse
from app.schemas.response import PaginatedData
from app.services.analytics_service import _date_label, _period_dates
from app.services.garage_service import _with_logo_url
from app.services.job_service import _with_photo_urls


def validate_dates(start_date, end_date):
    if start_date and end_date and start_date > end_date:
        raise BadRequestException("start_date must be before or equal to end_date.")


class AdminService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AdminRepository(session)

    async def audit(self, actor_id, action, resource_id=None, details=None):
        dedicated = await self.session.get(AdminAccount, actor_id)
        self.session.add(AdminAuditLog(
            actor_id=None if dedicated else actor_id,
            admin_account_id=actor_id if dedicated else None,
            action=action, resource_id=resource_id, details=details or {},
        ))
        # A failed audit write fails the request; status and audit commit atomically.
        await self.session.flush()

    async def page(self, query, schema, page, page_size, transform=None):
        rows, total = await self.repo.page(query, page, page_size)
        items = [schema.model_validate(row) for row in rows]
        if transform:
            items = [transform(item) for item in items]
        return PaginatedData(
            items=items, total=total, page=page, page_size=page_size,
            pages=max(1, (total + page_size - 1) // page_size),
        )

    async def user_detail(self, user_id):
        user = await self.repo.get_user(user_id)
        if not user:
            raise NotFoundException("User not found.")
        garages = (await self.session.execute(self.repo.garages_query(user_id=user_id))).scalars().all()
        return AdminUserDetail(
            **UserResponse.model_validate(user).model_dump(),
            garages=[_with_logo_url(GarageResponse.model_validate(g)) for g in garages],
        )

    async def set_user_status(self, actor: User, user_id, is_active):
        user = (await self.session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None)).with_for_update()
        )).scalar_one_or_none()
        if not user:
            raise NotFoundException("User not found.")
        if not is_active and (user.id == actor.id or user.role == UserRole.ADMIN.value):
            raise BadRequestException("Admin accounts cannot be deactivated through this endpoint.")
        before = user.is_active
        user.is_active = is_active
        user.updated_at = datetime.now(timezone.utc)
        if not is_active:
            # Already issued JWTs are also denied by the active-account check.
            await RefreshTokenRepository(self.session).revoke_all_for_user(user.id)
            user.otp = None
            user.otp_expires_at = None
        await self.audit(actor.id, "users.status", user.id, {
            "previous_is_active": before, "is_active": is_active,
        })
        return UserResponse.model_validate(user)

    async def garage_detail(self, garage_id):
        garage = await self.repo.get_garage(garage_id)
        if not garage:
            raise NotFoundException("Garage not found.")
        counts = await self.repo.status_counts(garage_id)
        return AdminGarageDetail(
            **_with_logo_url(GarageResponse.model_validate(garage)).model_dump(),
            total_jobs=sum(counts.values()), completed_jobs=counts["COMPLETED"],
            total_revenue=await self.repo.revenue(garage_id),
            billing_issue_count=await self.repo.count(
                self.repo.jobs_query(garage_id=garage_id, billing_issues=True),
            ),
        )

    async def job_detail(self, job_id):
        job = await self.repo.get_job(job_id)
        if not job:
            raise NotFoundException("Job not found.")
        return _with_photo_urls(JobDetailResponse.model_validate(job))

    async def dashboard(self):
        today = date.today()
        counts = await self.repo.status_counts()
        return AdminDashboardResponse(
            total_users=await self.repo.count(self.repo.users_query()),
            active_users=await self.repo.count(self.repo.users_query(is_active=True)),
            total_garages=await self.repo.count(self.repo.garages_query()),
            total_jobs=sum(counts.values()),
            jobs_today=await self.repo.count(self.repo.jobs_query(date_from=today, date_to=today)),
            status_counts=counts,
            total_bookings=await self.repo.count(self.repo.bookings_query()),
            pending_bookings=await self.repo.count(self.repo.bookings_query(status="PENDING")),
            revenue_today=await self.repo.revenue(start_date=today, end_date=today),
            revenue_this_month=await self.repo.revenue(start_date=today.replace(day=1), end_date=today),
            total_revenue=await self.repo.revenue(),
            billing_issue_count=await self.repo.count(self.repo.jobs_query(billing_issues=True)),
        )

    async def analytics(self, garage_id, period, start_date, end_date):
        if period == "custom" and (not start_date or not end_date):
            raise BadRequestException("start_date and end_date are required for custom period.")
        validate_dates(start_date, end_date)
        if garage_id and not await self.repo.get_garage(garage_id):
            raise NotFoundException("Garage not found.")
        start, end, trunc = _period_dates(period, start_date, end_date)
        counts = await self.repo.status_counts(garage_id, start, end)
        jobs, revenues = await self.repo.time_series(garage_id, start, end, trunc)
        merged = {}
        for row in jobs:
            merged[row.bucket] = {"job_count": row.count, "completed_count": 0, "revenue": 0}
        for row in revenues:
            merged.setdefault(row.bucket, {"job_count": 0})
            merged[row.bucket].update(completed_count=row.count, revenue=row.revenue)
        return AdminAnalyticsResponse(
            garage_id=garage_id, period=period, start_date=start, end_date=end,
            total_jobs=sum(counts.values()), total_revenue=await self.repo.revenue(garage_id, start, end),
            status_counts=counts,
            graph_data=[AdminTimeSeriesPoint(
                label=_date_label(bucket, trunc), **merged[bucket],
            ) for bucket in sorted(merged)],
        )
