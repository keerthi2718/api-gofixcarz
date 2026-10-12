from typing import Annotated
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update

from app.api.v1.admin import DBSession, Page, PageSize
from app.core.admin_policy import PERMISSIONS, ROLES, effective_permissions, require_permission
from app.core.admin_read_filters import reject_unknown_admin_query
from app.dependencies.auth import CurrentAdmin, get_current_admin
from app.models.admin_account import AdminAccount, AdminSession
from app.models.garage import Garage
from app.schemas.admin_security import AdminRoleAssignment
from app.schemas.response import APIResponse
from app.services.admin_service import AdminService

router = APIRouter(dependencies=[Depends(get_current_admin), Depends(reject_unknown_admin_query)])


def staff_row(account):
    return {
        "id": account.id, "display_name": account.name, "email": account.email,
        "is_active": account.is_active, "role_ids": account.role_ids,
        "permissions": sorted(effective_permissions(account)),
        "data_scope": {"type": "PLATFORM" if account.garage_scope is None else "GARAGES",
                       "garage_ids": account.garage_scope or []},
        "mfa_enrolled": bool(account.mfa_secret_encrypted), "mfa_required": account.mfa_required,
    }


@router.get("/permissions", response_model=APIResponse)
async def permissions(admin: CurrentAdmin, session: DBSession):
    await AdminService(session).audit(admin.id, "security.permissions")
    return APIResponse.ok(data={"items": [{"code": p, "description": p.replace(".", " ")} for p in sorted(PERMISSIONS)]})


@router.get("/roles", response_model=APIResponse)
async def roles(admin: CurrentAdmin, session: DBSession):
    await AdminService(session).audit(admin.id, "security.roles")
    return APIResponse.ok(data={"items": [
        {"id": role, "name": role.removeprefix("role_").title(), "permissions": permissions}
        for role, permissions in ROLES.items()
    ]})


@router.get("/staff", response_model=APIResponse)
async def staff(
    admin: CurrentAdmin, session: DBSession,
    search: Annotated[str | None, Query(max_length=200)] = None,
    is_active: bool | None = None, page: Page = 1, page_size: PageSize = 20,
):
    query = select(AdminAccount).order_by(AdminAccount.created_at.desc(), AdminAccount.id)
    if search:
        query = query.where(or_(AdminAccount.name.ilike(f"%{search}%"), AdminAccount.email.ilike(f"%{search}%")))
    if is_active is not None:
        query = query.where(AdminAccount.is_active == is_active)
    rows, total = await AdminService(session).repo.page(query, page, page_size)
    await AdminService(session).audit(admin.id, "security.staff")
    return APIResponse.ok(data={"items": [staff_row(a) for a in rows], "total": total, "page": page,
                               "page_size": page_size, "pages": max(1, (total + page_size - 1)//page_size)})


@router.put("/staff/{admin_id}/roles", response_model=APIResponse)
async def assign_roles(admin_id: UUID, data: AdminRoleAssignment, admin: CurrentAdmin, session: DBSession):
    access = require_permission(session, "security.manage", recent_mfa=True)
    if not isinstance(admin, AdminAccount) or access["garage_ids"] is not None:
        raise HTTPException(403, "PRIVILEGE_ESCALATION_DENIED")
    if admin_id == admin.id:
        raise HTTPException(403, "Self role or scope changes are not permitted")
    # Lock in stable order: two grantors cannot concurrently remove the final security admin.
    accounts = (await session.execute(select(AdminAccount).order_by(AdminAccount.id).with_for_update())).scalars().all()
    target = next((a for a in accounts if a.id == admin_id), None)
    if not target:
        raise HTTPException(404, "Staff account not found")
    if "role_ceo" in target.role_ids and "role_ceo" not in data.role_ids:
        others = [a for a in accounts if a.id != target.id and a.is_active and "role_ceo" in a.role_ids]
        if not others:
            raise HTTPException(409, "LAST_SECURITY_ADMIN")
    if data.data_scope.type == "GARAGES":
        garages = (await session.execute(select(Garage.id).where(
            Garage.id.in_(data.data_scope.garage_ids), Garage.deleted_at.is_(None),
        ))).scalars().all()
        if len(garages) != len(data.data_scope.garage_ids):
            raise HTTPException(422, "Invalid garage scope")
    before = {"role_ids": target.role_ids, "garage_scope": target.garage_scope}
    target.role_ids = list(data.role_ids)
    target.garage_scope = sorted(map(str, data.data_scope.garage_ids)) if data.data_scope.type == "GARAGES" else None
    target.credential_version += 1
    await session.execute(update(AdminSession).where(
        AdminSession.admin_account_id == target.id, AdminSession.revoked_at.is_(None),
    ).values(revoked_at=datetime.now(timezone.utc)))
    await AdminService(session).audit(admin.id, "security.roles.write", target.id, {
        "before": before, "after": {"role_ids": target.role_ids, "garage_scope": target.garage_scope},
        "reason": data.reason,
    })
    return APIResponse.ok(data=staff_row(target))
