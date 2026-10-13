"""First-phase admin reads. No operational or financial mutation powers."""
from dataclasses import replace
from datetime import date, datetime, timezone as utc_timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_read_filters import AdminReadFilters, reject_unknown_admin_query
from app.database.session import get_session
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.models.user import AccountStatus
from app.schemas.admin import AdminAuditResponse
from app.schemas.admin_monitoring import (
    AdminActivityPage, AdminBookingDetail, AdminBookingExceptionsResponse,
    AdminFunnelResponse, AdminOwnerDetailResponse, AdminOwnerPage, AdminTimelineEvent,
)
from app.schemas.response import APIResponse, PaginatedData
from app.services.admin_monitoring_service import AdminMonitoringService


from app.core.admin_privacy import AdminPrivacyRoute
router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[Depends(get_current_admin), Depends(reject_unknown_admin_query)])
DBSession = Annotated[AsyncSession, Depends(get_session)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def read_filters(
    date_from: date | None = None, date_to: date | None = None,
    timezone: Annotated[str, Query(max_length=64)] = "UTC",
    city: Annotated[str | None, Query(max_length=100)] = None,
    garage_id: UUID | None = None,
):
    return AdminReadFilters(date_from, date_to, timezone, city, garage_id)


Filters = Annotated[AdminReadFilters, Depends(read_filters)]


def read_metadata(filters):
    return {
        "filters": filters.metadata(), "generated_at": datetime.now(utc_timezone.utc),
        "metric_bases": {
            "bookings": "booking.created_at",
            "jobs_created": "job.created_at",
            "completed_jobs": "current COMPLETED state within job.created_at cohort",
            "completed_job_amount_paise": "job.completed_at; recorded final amounts, not captured payments",
        },
        "unavailable_data_sources": ["reviews", "payment_collections"],
    }


@router.get("/garage-owners", response_model=APIResponse[AdminOwnerPage])
async def owners(
    admin: CurrentAdmin, session: DBSession, filters: Filters,
    search: Annotated[str | None, Query(max_length=200)] = None,
    status: AccountStatus | None = None, include_deleted: bool = False,
    min_rating: Annotated[float | None, Query(ge=1, le=5)] = None,
    page: Page = 1, page_size: PageSize = 20,
):
    service = AdminMonitoringService(session)
    result = await service.owners(filters, search, status, include_deleted, page, page_size, min_rating)
    await service.audit(admin.id, "garage_owners.list")
    return APIResponse.ok(data={**result.model_dump(), **read_metadata(filters)})


@router.get("/garage-owners/{owner_id}", response_model=APIResponse[AdminOwnerDetailResponse])
async def owner_detail(
    owner_id: UUID, admin: CurrentAdmin, session: DBSession, filters: Filters,
    include_deleted: bool = False,
):
    service = AdminMonitoringService(session)
    result = await service.owner_detail(owner_id, filters, include_deleted)
    await service.audit(admin.id, "garage_owners.read", owner_id)
    return APIResponse.ok(data={**result.model_dump(), **read_metadata(filters)})


# Static operation must precede the UUID booking-detail route.
@router.get("/bookings/exception-statistics", response_model=APIResponse)
async def booking_exceptions(admin: CurrentAdmin, session: DBSession, filters: Filters,
                             group_by: Annotated[str | None, Query(max_length=100)] = None):
    service = AdminMonitoringService(session)
    result = await service.exceptions(filters, group_by)
    await service.audit(admin.id, "bookings.exceptions")
    return APIResponse.ok(data=result)


@router.get("/bookings/{booking_id}", response_model=APIResponse[AdminBookingDetail])
async def booking_detail(booking_id: UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminMonitoringService(session)
    result = await service.booking_detail(booking_id)
    await service.audit(admin.id, "bookings.read", booking_id)
    return APIResponse.ok(data=result)


@router.get("/jobs/{job_id}/timeline", response_model=APIResponse[PaginatedData[AdminTimelineEvent]])
async def timeline(
    job_id: UUID, admin: CurrentAdmin, session: DBSession, page: Page = 1, page_size: PageSize = 20,
):
    service = AdminMonitoringService(session)
    result = await service.timeline(job_id, page, page_size)
    await service.audit(admin.id, "jobs.timeline", job_id)
    return APIResponse.ok(data=result)


@router.get("/audit-logs/{audit_id}", response_model=APIResponse[AdminAuditResponse])
async def audit_detail(audit_id: UUID, admin: CurrentAdmin, session: DBSession):
    service = AdminMonitoringService(session)
    result = await service.audit_detail(audit_id)
    await service.audit(admin.id, "audit.read", audit_id)
    return APIResponse.ok(data=result)


@router.get("/activity", response_model=APIResponse[AdminActivityPage])
async def activity(
    admin: CurrentAdmin, session: DBSession, filters: Filters,
    owner_id: UUID | None = None, customer_id: UUID | None = None,
    booking_id: UUID | None = None, job_id: UUID | None = None,
    event_type: Literal["BOOKING_CREATED", "JOB_CREATED", "JOB_COMPLETED", "JOB_STATUS_RECORDED",
                        "BOOKING_ACCEPTED", "BOOKING_REJECTED", "BOOKING_CONVERTED", "BOOKING_CANCELLED",
                        "BOOKING_EXPIRED", "INVOICE_ISSUED", "PAYMENT_CAPTURED", "PAYMENT_FAILED",
                        "REFUND_SETTLED", "REVIEW_PUBLISHED"] | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    filters = replace(filters, owner_id=owner_id)
    service = AdminMonitoringService(session)
    result = await service.activity(filters, page, page_size, customer_id=customer_id,
                                    booking_id=booking_id, job_id=job_id, event_type=event_type)
    recorded = await service.recorded_types(filters, customer_id=customer_id, booking_id=booking_id,
                                           job_id=job_id, event_type=event_type)
    categories = {
        "booking_decisions": {"BOOKING_ACCEPTED", "BOOKING_REJECTED", "BOOKING_CANCELLED", "BOOKING_EXPIRED"},
        "invoices": {"INVOICE_ISSUED"}, "payments": {"PAYMENT_CAPTURED", "PAYMENT_FAILED"},
        "reviews": {"REVIEW_PUBLISHED"},
    }
    restricted = ["invoices", "payments"] if "finance.read" not in session.info["admin_access"]["permissions"] else []
    await service.audit(admin.id, "activity.list")
    return APIResponse.ok(data={
        **result.model_dump(), "filters": filters.metadata(), "generated_at": datetime.now(utc_timezone.utc),
        "unavailable_history": [key for key, types in categories.items() if not recorded & types and key not in restricted],
        "restricted_history": restricted,
    })


@router.get("/activity/service-funnels/{booking_id}", response_model=APIResponse[AdminFunnelResponse])
async def funnel(
    booking_id: UUID, admin: CurrentAdmin, session: DBSession, page: Page = 1, page_size: PageSize = 20,
):
    service = AdminMonitoringService(session)
    result = await service.funnel(booking_id, AdminReadFilters(), page, page_size)
    await service.audit(admin.id, "activity.funnel", booking_id)
    return APIResponse.ok(data=result)
