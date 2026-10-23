import uuid
from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.admin_read_filters import AdminReadFilters
from app.models.garage import Garage
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
from app.services.analytics_service import _date_label
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

    async def user_detail(self, user_id, include_deleted=False):
        user = await self.repo.get_user(user_id, include_deleted=include_deleted)
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
            admin_version=garage.admin_version,
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

    async def dashboard(self, filters=None):
        filters = filters or AdminReadFilters()
        if filters.garage_id and not await self.repo.get_garage(filters.garage_id):
            raise NotFoundException("Garage not found.")
        today = datetime.now(ZoneInfo(filters.timezone)).date()
        counts = await self.repo.status_counts(filters=filters)
        users = self.repo.users_query()
        if filters.city is not None or filters.garage_id is not None:
            users = users.where(User.id.in_(
                self.repo.garages_query(filters=filters).with_only_columns(Garage.user_id).order_by(None)
            ))
        today_filters = replace(filters, date_from=max(filters.date_from or today, today),
                                date_to=min(filters.date_to or today, today)) if (
            (not filters.date_from or filters.date_from <= today) and
            (not filters.date_to or filters.date_to >= today)
        ) else None
        return AdminDashboardResponse(
            total_users=await self.repo.count(users),
            active_users=await self.repo.count(users.where(User.is_active.is_(True))),
            total_garages=await self.repo.count(self.repo.garages_query(filters=filters)),
            total_jobs=sum(counts.values()),
            jobs_today=await self.repo.count(self.repo.jobs_query(filters=today_filters)) if today_filters else 0,
            status_counts=counts,
            total_bookings=await self.repo.count(self.repo.bookings_query(filters=filters)),
            pending_bookings=await self.repo.count(self.repo.bookings_query(status="PENDING", filters=filters)),
            revenue_today=await self.repo.revenue(start_date=today, end_date=today, filters=filters),
            revenue_this_month=await self.repo.revenue(start_date=today.replace(day=1), end_date=today, filters=filters),
            total_revenue=await self.repo.revenue(filters=filters),
            billing_issue_count=await self.repo.count(self.repo.jobs_query(billing_issues=True, filters=filters)),
            filters=filters.metadata(), generated_at=datetime.now(timezone.utc),
            metric_bases={
                "users_and_garages": "current inventory; dates do not filter inventory",
                "jobs_and_bookings": "created_at cohort; current persisted status",
                "revenue": "completed_at; recorded job final amounts in INR, not payment collections",
            },
        )

    async def analytics(self, garage_id, period, start_date, end_date, filters=None):
        if period == "custom" and (not start_date or not end_date):
            raise BadRequestException("start_date and end_date are required for custom period.")
        validate_dates(start_date, end_date)
        if garage_id and not await self.repo.get_garage(garage_id):
            raise NotFoundException("Garage not found.")
        filters = filters or AdminReadFilters()
        today = datetime.now(ZoneInfo(filters.timezone)).date()
        if period == "daily":
            start, end, trunc = today - timedelta(days=6), today, "day"
        elif period == "weekly":
            start, end, trunc = today - timedelta(weeks=4), today, "week"
        elif period == "monthly":
            start, end, trunc = today.replace(day=1) - timedelta(days=335), today, "month"
        else:
            start, end, trunc = start_date, end_date, "day"
        # Unlike the owner analytics helper, explicit admin dates apply to every period.
        start, end = start_date or start, end_date or end
        filters = replace(filters, date_from=start, date_to=end, garage_id=garage_id)
        counts = await self.repo.status_counts(filters=filters)
        jobs, revenues = await self.repo.time_series(garage_id, start, end, trunc, filters=filters)
        merged = {}
        for row in jobs:
            merged[row.bucket] = {"job_count": row.count, "completed_count": 0, "revenue": 0}
        for row in revenues:
            merged.setdefault(row.bucket, {"job_count": 0})
            merged[row.bucket].update(completed_count=row.count, revenue=row.revenue)
        return AdminAnalyticsResponse(
            garage_id=garage_id, period=period, start_date=start, end_date=end,
            total_jobs=sum(counts.values()), total_revenue=await self.repo.revenue(filters=filters),
            status_counts=counts,
            graph_data=[AdminTimeSeriesPoint(
                label=_date_label(bucket, trunc), **merged[bucket],
            ) for bucket in sorted(merged)],
            filters=filters.metadata(), generated_at=datetime.now(timezone.utc),
            metric_bases={
                "job_count_and_status_counts": "job.created_at; current status",
                "completed_count": "job.completed_at; current COMPLETED status",
                "revenue": "job.completed_at; recorded final amounts in INR, not collections",
            },
        )
