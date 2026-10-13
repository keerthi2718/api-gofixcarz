import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.core.admin_read_filters import AdminReadFilters, reject_unknown_admin_query
from app.api.v1.admin_monitoring import Filters
from app.core.admin_privacy import AdminPrivacyRoute

# Router-wide protection prevents accidentally adding an unguarded admin route.
router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[Depends(get_current_admin), Depends(reject_unknown_admin_query)])
DBSession = Annotated[AsyncSession, Depends(get_session)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(max_length=200)]


@router.get("/menus", response_model=APIResponse)
async def admin_menus(admin: CurrentAdmin, session: DBSession):
    await AdminService(session).audit(admin.id, "menus.read")
    from app.core.admin_route_permissions import enforce_route_permission
    from app.services.admin_auth_service import authorized_menus
    return APIResponse.ok(data={"menus": authorized_menus(session.info["admin_access"]["permissions"])})


@router.get("/me", response_model=APIResponse)
async def admin_me(admin: CurrentAdmin, session: DBSession):
    """Admin identity; no owned garage is required."""
    await AdminService(session).audit(admin.id, "me.read")
    schema = AdminIdentity if isinstance(admin, AdminAccount) else UserResponse
    result = schema.model_validate(admin).model_dump(mode="json")
    access = session.info["admin_access"]
    result.update(permissions=sorted(access["permissions"]),
                  role_ids=admin.role_ids if isinstance(admin, AdminAccount) else [],
                  data_scope={"type": "PLATFORM" if access["garage_ids"] is None else "GARAGES",
                              "garage_ids": access["garage_ids"] or []})
    return APIResponse.ok(data=result)


@router.get("/dashboard", response_model=APIResponse)
async def dashboard(admin: CurrentAdmin, session: DBSession, filters: Filters,
                    snapshot_id: uuid.UUID | None = None):
    service = AdminService(session)
    from app.services.admin_metrics_service import AdminMetricsService
    metrics = AdminMetricsService(session)
    snapshot = await metrics.dataset(filters, snapshot_id)
    if snapshot_id:
        result = snapshot.payload.get("dashboard")
        if result is None:
            raise HTTPException(409, "SNAPSHOT_DATASET_MISMATCH")
    else:
        from fastapi.encoders import jsonable_encoder
        result = jsonable_encoder(await service.dashboard(filters))
        snapshot.payload = {**snapshot.payload, "dashboard": result}
    result = {**result, "snapshot_id": snapshot.id, "generated_at": snapshot.payload["generated_at"],
              "extended_metrics": {**metrics.finance(snapshot, filters), **metrics.metadata(snapshot)}}
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
    city: Annotated[str | None, Query(max_length=100)] = None,
    operational_status: Literal["ACTIVE", "SUSPENDED"] | None = None,
    verification_status: Literal["UNVERIFIED", "VERIFIED", "REJECTED"] | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    service = AdminService(session)
    query = service.repo.garages_query(search, user_id, filters=AdminReadFilters(city=city))
    from app.models.garage import Garage
    if operational_status:
        query = query.where(Garage.operational_status == operational_status)
    if verification_status:
        query = query.where(Garage.verification_status == verification_status)
    result = await service.page(
        query,
        GarageResponse, page, page_size, _with_logo_url,
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
    admin: CurrentAdmin, session: DBSession, filters: Filters,
    status: JobStatus | None = None, search: Search = None,
    customer_id: uuid.UUID | None = None,
    booking_id: uuid.UUID | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    service = AdminService(session)
    query = service.repo.jobs_query(status=status, search=search, filters=filters)
    if customer_id is not None:
        from app.models.job import Job
        query = query.where(Job.customer_id == customer_id)
    if booking_id is not None:
        from app.models.job import Job
        query = query.where(Job.booking_id == booking_id)
    result = await service.page(
        query,
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
    admin: CurrentAdmin, session: DBSession, filters: Filters,
    customer_id: uuid.UUID | None = None, search: Search = None,
    status: BookingStatus | None = None, page: Page = 1, page_size: PageSize = 20,
):
    service = AdminService(session)
    result = await service.page(
        service.repo.bookings_query(status=status, filters=filters, customer_id=customer_id, search=search),
        BookingResponse, page, page_size,
    )
    await service.audit(admin.id, "bookings.list")
    return APIResponse.ok(data=result)


@router.get("/analytics", response_model=APIResponse)
async def analytics(
    admin: CurrentAdmin, session: DBSession, filters: Filters,
    period: Literal["daily", "weekly", "monthly", "custom"] = "monthly",
    start_date: date | None = None, end_date: date | None = None,
    snapshot_id: uuid.UUID | None = None,
):
    service = AdminService(session)
    if (start_date and filters.date_from and start_date != filters.date_from) or (
        end_date and filters.date_to and end_date != filters.date_to
    ):
        raise HTTPException(422, "Conflicting date aliases")
    result = await service.analytics(filters.garage_id, period, start_date or filters.date_from,
                                     end_date or filters.date_to, filters=filters)
    from dataclasses import replace
    from fastapi.encoders import jsonable_encoder
    from app.services.admin_metrics_service import AdminMetricsService
    metrics = AdminMetricsService(session)
    snapshot_filters = replace(filters, date_from=start_date or filters.date_from, date_to=end_date or filters.date_to)
    snapshot = await metrics.dataset(snapshot_filters, snapshot_id)
    key = "analytics_" + period
    if snapshot_id:
        result = snapshot.payload.get(key)
        if result is None:
            raise HTTPException(409, "SNAPSHOT_DATASET_MISMATCH")
    else:
        result = jsonable_encoder(result)
        snapshot.payload = {**snapshot.payload, key: result}
    result = {**result, "snapshot_id": snapshot.id, "generated_at": snapshot.payload["generated_at"]}
    await service.audit(admin.id, "analytics.read", filters.garage_id)
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
    timezone: Annotated[str, Query(max_length=64)] = "UTC",
    page: Page = 1, page_size: PageSize = 20,
):
    validate_dates(date_from, date_to)
    service = AdminService(session)
    result = await service.page(
        service.repo.audit_query(actor_id, action, filters=AdminReadFilters(date_from, date_to, timezone)),
        AdminAuditResponse, page, page_size,
    )
    await service.audit(admin.id, "audit.list")
    return APIResponse.ok(data=result)
