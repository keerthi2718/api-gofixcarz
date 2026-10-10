import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.models.booking import BookingStatus
from app.models.job import JobStatus
from app.models.user import UserRole
from app.schemas.admin import (
    AdminAnalyticsResponse, AdminAuditResponse, AdminDashboardResponse,
    AdminGarageDetail, AdminUserDetail, AdminUserStatusUpdate,
)
from app.schemas.auth import UserResponse
from app.schemas.admin_auth import AdminIdentity
from app.models.admin_account import AdminAccount
from app.services.admin_auth_service import MENUS
from app.schemas.booking import BookingResponse
from app.schemas.garage import GarageResponse
from app.schemas.job import JobDetailResponse, JobResponse
from app.schemas.response import APIResponse, PaginatedData
from app.services.admin_service import AdminService, validate_dates
from app.services.garage_service import _with_logo_url
from app.services.job_service import _with_photo_urls

# Router-wide protection prevents accidentally adding an unguarded admin route.
router = APIRouter(dependencies=[Depends(get_current_admin)])
DBSession = Annotated[AsyncSession, Depends(get_session)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(max_length=200)]


@router.get("/menus", response_model=APIResponse)
async def admin_menus(admin: CurrentAdmin, session: DBSession):
    await AdminService(session).audit(admin.id, "menus.read")
    return APIResponse.ok(data={"menus": [menu.model_dump() for menu in MENUS]})


@router.get("/me", response_model=APIResponse[UserResponse | AdminIdentity])
async def admin_me(admin: CurrentAdmin, session: DBSession):
    """Admin identity; no owned garage is required."""
    await AdminService(session).audit(admin.id, "me.read")
    schema = AdminIdentity if isinstance(admin, AdminAccount) else UserResponse
    return APIResponse.ok(data=schema.model_validate(admin))


@router.get("/dashboard", response_model=APIResponse[AdminDashboardResponse])
async def dashboard(admin: CurrentAdmin, session: DBSession):
    service = AdminService(session)
    result = await service.dashboard()
    await service.audit(admin.id, "dashboard.read")
    return APIResponse.ok(data=result)


@router.get("/users", response_model=APIResponse[PaginatedData[UserResponse]])
async def users(
    admin: CurrentAdmin, session: DBSession, search: Search = None,
    is_active: bool | None = None, role: UserRole | None = None,
    include_deleted: bool = False,
    page: Page = 1, page_size: PageSize = 20,
):
    service = AdminService(session)
    result = await service.page(
        service.repo.users_query(search, is_active, role, include_deleted=include_deleted), UserResponse, page, page_size,
    )
    await service.audit(admin.id, "users.list")
    return APIResponse.ok(data=result)


@router.get("/users/{user_id}", response_model=APIResponse[AdminUserDetail])
async def user_detail(user_id: uuid.UUID, admin: CurrentAdmin, session: DBSession, include_deleted: bool = False):
    service = AdminService(session)
    result = await service.user_detail(user_id, include_deleted=include_deleted)
    await service.audit(admin.id, "users.read", user_id)
    return APIResponse.ok(data=result)


@router.patch("/users/{user_id}/status", response_model=APIResponse[UserResponse])
async def user_status(
    user_id: uuid.UUID, data: AdminUserStatusUpdate, admin: CurrentAdmin, session: DBSession,
):
    """Activate/deactivate garage-owner accounts; admin deactivation is disallowed."""
    result = await AdminService(session).set_user_status(admin, user_id, data.is_active)
    return APIResponse.ok(data=result, message="Account status updated")


@router.get("/garages", response_model=APIResponse[PaginatedData[GarageResponse]])
async def garages(
    admin: CurrentAdmin, session: DBSession, search: Search = None, user_id: uuid.UUID | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    service = AdminService(session)
    result = await service.page(
        service.repo.garages_query(search, user_id), GarageResponse, page, page_size, _with_logo_url,
    )
    await service.audit(admin.id, "garages.list")
    return APIResponse.ok(data=result)


@router.get("/garages/{garage_id}", response_model=APIResponse[AdminGarageDetail])
async def garage_detail(garage_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminService(session)
    result = await service.garage_detail(garage_id)
    await service.audit(admin.id, "garages.read", garage_id)
    return APIResponse.ok(data=result)


@router.get("/jobs", response_model=APIResponse[PaginatedData[JobResponse]])
async def jobs(
    admin: CurrentAdmin, session: DBSession, garage_id: uuid.UUID | None = None,
    status: JobStatus | None = None, search: Search = None,
    date_from: date | None = None, date_to: date | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    validate_dates(date_from, date_to)
    service = AdminService(session)
    result = await service.page(
        service.repo.jobs_query(garage_id, status, search, date_from, date_to),
        JobResponse, page, page_size, _with_photo_urls,
    )
    await service.audit(admin.id, "jobs.list")
    return APIResponse.ok(data=result)


@router.get("/jobs/{job_id}", response_model=APIResponse[JobDetailResponse])
async def job_detail(job_id: uuid.UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminService(session)
    result = await service.job_detail(job_id)
    await service.audit(admin.id, "jobs.read", job_id)
    return APIResponse.ok(data=result)


@router.get("/bookings", response_model=APIResponse[PaginatedData[BookingResponse]])
async def bookings(
    admin: CurrentAdmin, session: DBSession, garage_id: uuid.UUID | None = None,
    status: BookingStatus | None = None, page: Page = 1, page_size: PageSize = 20,
):
    service = AdminService(session)
    result = await service.page(
        service.repo.bookings_query(garage_id, status), BookingResponse, page, page_size,
    )
    await service.audit(admin.id, "bookings.list")
    return APIResponse.ok(data=result)


@router.get("/analytics", response_model=APIResponse[AdminAnalyticsResponse])
async def analytics(
    admin: CurrentAdmin, session: DBSession, garage_id: uuid.UUID | None = None,
    period: Literal["daily", "weekly", "monthly", "custom"] = "monthly",
    start_date: date | None = None, end_date: date | None = None,
):
    service = AdminService(session)
    result = await service.analytics(garage_id, period, start_date, end_date)
    await service.audit(admin.id, "analytics.read", garage_id)
    return APIResponse.ok(data=result)


@router.get("/billing/issues", response_model=APIResponse[PaginatedData[JobResponse]])
async def billing_issues(
    admin: CurrentAdmin, session: DBSession, garage_id: uuid.UUID | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    """Read-only review of completed jobs missing final amount, billing or completion time."""
    service = AdminService(session)
    result = await service.page(
        service.repo.jobs_query(garage_id=garage_id, billing_issues=True),
        JobResponse, page, page_size, _with_photo_urls,
    )
    await service.audit(admin.id, "billing.issues")
    return APIResponse.ok(data=result)


@router.get("/audit-logs", response_model=APIResponse[PaginatedData[AdminAuditResponse]])
async def audit_logs(
    admin: CurrentAdmin, session: DBSession, actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None, date_to: date | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    validate_dates(date_from, date_to)
    service = AdminService(session)
    result = await service.page(
        service.repo.audit_query(actor_id, action, date_from, date_to),
        AdminAuditResponse, page, page_size,
    )
    await service.audit(admin.id, "audit.list")
    return APIResponse.ok(data=result)
