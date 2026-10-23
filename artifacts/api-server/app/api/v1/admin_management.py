"""Additional admin management contracts and a proof-bound invitation acceptance."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from app.api.v1.admin_monitoring import Filters, DBSession, Page, PageSize
from app.core.admin_privacy import AdminPrivacyRoute
from app.core.admin_read_filters import reject_unknown_admin_query
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.models.job import JobStatus
from app.schemas.admin_management import (
    GaragePatch, InvitationAccept, InvitationCreate, RoleCreate, RolePatch, VersionedDelete,
)
from app.schemas.response import APIResponse
from app.services.admin_garage_management import AdminGarageManagement
from app.services.admin_management_service import AdminManagementService, manager
from app.services.admin_service import AdminService

router = APIRouter(route_class=AdminPrivacyRoute, dependencies=[
    Depends(get_current_admin), Depends(reject_unknown_admin_query)])
accept_router = APIRouter()


@router.get("/garages/{garage_id}/metrics", response_model=APIResponse)
async def garage_metrics(garage_id: UUID, admin: CurrentAdmin, session: DBSession, filters: Filters,
                         status: JobStatus | None = None):
    result = await AdminGarageManagement(session).metrics(garage_id, filters, status)
    await AdminService(session).audit(admin.id, "garages.metrics", garage_id)
    return APIResponse.ok(data=result)


@router.get("/garages/{garage_id}/job-card-count", response_model=APIResponse)
async def job_card_count(garage_id: UUID, admin: CurrentAdmin, session: DBSession, filters: Filters,
                         status: JobStatus | None = None):
    result = await AdminGarageManagement(session).metrics(garage_id, filters, status)
    await AdminService(session).audit(admin.id, "garages.job_card_count", garage_id)
    return APIResponse.ok(data={key: result[key] for key in (
        "garage_id", "job_card_count", "filters", "generated_at", "metric_basis")})


@router.patch("/garages/{garage_id}", response_model=APIResponse)
async def patch_garage(garage_id: UUID, data: GaragePatch, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminGarageManagement(session).patch(admin, garage_id, data))


@router.get("/reports/garage-performance", response_model=APIResponse)
async def garage_performance(admin: CurrentAdmin, session: DBSession, filters: Filters,
                             status: JobStatus | None = None, page: Page = 1, page_size: PageSize = 20):
    from app.core.admin_policy import require_permission
    require_permission(session, "garages.read")
    require_permission(session, "jobs.read")
    result = await AdminGarageManagement(session).report(filters, status, page, page_size)
    await AdminService(session).audit(admin.id, "reports.garage_performance")
    return APIResponse.ok(data=result)


@router.post("/roles", response_model=APIResponse, status_code=201)
async def create_role(data: RoleCreate, admin: CurrentAdmin, session: DBSession):
    return APIResponse.created(data=await AdminManagementService(session).create_role(admin, data))


@router.patch("/roles/{role_id}", response_model=APIResponse)
async def patch_role(role_id: str, data: RolePatch, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminManagementService(session).change_role(admin, role_id, data))


@router.delete("/roles/{role_id}", response_model=APIResponse)
async def delete_role(role_id: str, data: VersionedDelete, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminManagementService(session).change_role(admin, role_id, data, delete=True))


@router.get("/invitations", response_model=APIResponse)
async def invitations(admin: CurrentAdmin, session: DBSession, page: Page = 1, page_size: PageSize = 20,
                       status: Literal["PENDING", "EXPIRED", "ACCEPTED", "REVOKED"] | None = None):
    manager(session, admin)
    result = await AdminManagementService(session).invitations(page, page_size, status)
    await AdminService(session).audit(admin.id, "security.invitations.list")
    return APIResponse.ok(data=result)


@router.post("/invitations", response_model=APIResponse, status_code=201)
async def create_invitation(data: InvitationCreate, admin: CurrentAdmin, session: DBSession):
    return APIResponse.created(data=await AdminManagementService(session).create_invitation(admin, data))


@router.post("/invitations/{invitation_id}/resend", response_model=APIResponse)
async def resend_invitation(invitation_id: UUID, data: VersionedDelete, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminManagementService(session).change_invitation(admin, invitation_id, data))


@router.delete("/invitations/{invitation_id}", response_model=APIResponse)
async def revoke_invitation(invitation_id: UUID, data: VersionedDelete, admin: CurrentAdmin, session: DBSession):
    return APIResponse.ok(data=await AdminManagementService(session).change_invitation(admin, invitation_id, data, revoke=True))


@accept_router.post("/admin-invitations/accept", response_model=APIResponse, status_code=201)
async def accept_invitation(data: InvitationAccept, session: DBSession):
    """No existing session required; the expiring, single-use proof is mandatory."""
    from fastapi import Response
    from fastapi.encoders import jsonable_encoder
    import json
    result = await AdminManagementService(session).accept(data)
    return Response(json.dumps(jsonable_encoder(APIResponse.created(data=result))),
                    status_code=201, media_type="application/json", headers={"Cache-Control": "no-store"})
