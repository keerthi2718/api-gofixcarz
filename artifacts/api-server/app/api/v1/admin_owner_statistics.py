import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from app.api.v1.admin import DBSession, Page, PageSize
from app.api.v1.admin_monitoring import Filters
from app.core.admin_privacy import AdminPrivacyRoute
from app.core.admin_read_filters import reject_unknown_admin_query
from app.core.admin_policy import require_permission
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.schemas.response import APIResponse
from app.services.admin_metrics_service import AdminMetricsService

router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[
    Depends(get_current_admin), Depends(reject_unknown_admin_query)])


@router.get("/garage-owner-statistics", response_model=APIResponse)
async def owner_statistics(
    admin: CurrentAdmin, session: DBSession, filters: Filters, snapshot_id: uuid.UUID | None = None,
    exclude_inactive: bool = False, sort: Literal["jobs_created_desc", "net_collected_amount_desc", "owner_name_asc"] = "jobs_created_desc",
    page: Page = 1, page_size: PageSize = 20,
):
    service = AdminMetricsService(session)
    snapshot = await service.dataset(filters, snapshot_id, exclude_inactive)
    rows = service.owner_rows(snapshot, filters)
    if sort == "net_collected_amount_desc":
        require_permission(session, "finance.read")
    if sort == "owner_name_asc":
        rows.sort(key=lambda r: (r["owner_name"].casefold(), r["owner_id"]))
    else:
        key = "jobs_created" if sort == "jobs_created_desc" else "net_collected_amount"
        rows.sort(key=lambda r: (-r[key], r["owner_id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    await service.audit("owner_statistics.list")
    return APIResponse.ok(data={**service.metadata(snapshot), "items": rows[(page-1)*page_size:page*page_size],
                               "total": len(rows), "page": page, "page_size": page_size,
                               "source_totals": service.totals(rows)})


@router.get("/garage-owner-statistics/summary", response_model=APIResponse)
async def owner_summary(admin: CurrentAdmin, session: DBSession, filters: Filters,
                        snapshot_id: uuid.UUID | None = None, exclude_inactive: bool = False):
    service = AdminMetricsService(session)
    snapshot = await service.dataset(filters, snapshot_id, exclude_inactive)
    await service.audit("owner_statistics.summary")
    return APIResponse.ok(data={**service.metadata(snapshot), **service.totals(service.owner_rows(snapshot, filters)),
                               "exclude_inactive": exclude_inactive})


@router.get("/garage-owner-statistics/{owner_id}", response_model=APIResponse)
async def owner_detail(owner_id: uuid.UUID, admin: CurrentAdmin, session: DBSession, filters: Filters,
                       snapshot_id: uuid.UUID | None = None, exclude_inactive: bool = False):
    service = AdminMetricsService(session)
    snapshot = await service.dataset(filters, snapshot_id, exclude_inactive)
    row = next((r for r in service.owner_rows(snapshot, filters) if r["owner_id"] == str(owner_id)), None)
    if not row:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    await service.audit("owner_statistics.read", owner_id)
    return APIResponse.ok(data={**service.metadata(snapshot), **row})


@router.get("/garage-owner-statistics/{owner_id}/trends", response_model=APIResponse)
async def owner_trends(owner_id: uuid.UUID, admin: CurrentAdmin, session: DBSession, filters: Filters,
                       snapshot_id: uuid.UUID | None = None, exclude_inactive: bool = False,
                       period: Literal["daily", "weekly", "monthly"] = "daily"):
    service = AdminMetricsService(session)
    snapshot = await service.dataset(filters, snapshot_id, exclude_inactive)
    if str(owner_id) not in snapshot.payload["owners"]:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    await service.audit("owner_statistics.trends", owner_id)
    return APIResponse.ok(data={**service.metadata(snapshot), "owner_id": owner_id, "period": period,
                               "series": service.trends(snapshot, filters, period, owner_id)})
