"""Persistent custom roles and manual invitations using existing admin resources.

Security writes serialize with staff assignment/acceptance so a role cannot be
deleted while being assigned. No mail provider or public admin signup is implied.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool
from app.core.admin_policy import PERMISSIONS, ROLES, require_permission
from app.core.admin_security import hash_admin_password
from app.models.admin_account import AdminAccount
from app.models.admin_operations import AdminResource
from app.models.garage import Garage
from app.services.admin_service import AdminService


def now():
    return datetime.now(timezone.utc)


async def security_lock(session):
    await session.execute(text("SELECT pg_advisory_xact_lock(72640181)"))


def manager(session, admin):
    require_permission(session, "security.manage", recent_mfa=True)
    if not isinstance(admin, AdminAccount) or "role_ceo" not in admin.role_ids or admin.garage_scope is not None:
        raise HTTPException(403, "PLATFORM_SECURITY_ADMIN_REQUIRED")


class AdminManagementService:
    def __init__(self, session):
        self.session = session

    async def audit(self, admin, action, resource_id, details):
        await AdminService(self.session).audit(admin.id, action, resource_id, details)

    async def roles(self):
        rows = (await self.session.execute(select(AdminResource).where(
            AdminResource.kind == "CUSTOM_ROLE", AdminResource.status == "ACTIVE",
        ).order_by(AdminResource.created_at, AdminResource.id))).scalars().all()
        return ([{"id": key, "name": key.removeprefix("role_").title(), "permissions": value,
                  "is_system": True, "version": 1} for key, value in ROLES.items()]
                + [self.role_row(row) for row in rows])

    def role_row(self, row):
        return {"id": row.payload["role_id"], "name": row.payload["name"],
                "permissions": row.payload["permissions"], "version": row.payload["version"],
                "is_system": False}

    async def validate_roles(self, role_ids, scope):
        if len(set(role_ids)) != len(role_ids):
            raise HTTPException(422, "DUPLICATE_ROLE")
        available = {r["id"] for r in await self.roles()}
        if set(role_ids) - available:
            raise HTTPException(422, "UNKNOWN_ROLE")
        if "role_ceo" in role_ids and scope.type != "PLATFORM":
            raise HTTPException(422, "CEO_REQUIRES_PLATFORM_SCOPE")
        if scope.type == "GARAGES":
            found = (await self.session.execute(select(Garage.id).where(
                Garage.id.in_(scope.garage_ids), Garage.deleted_at.is_(None),
            ))).scalars().all()
            if len(found) != len(scope.garage_ids):
                raise HTTPException(422, "INVALID_GARAGE_SCOPE")

    def validate_permissions(self, permissions):
        if set(permissions) - PERMISSIONS or len(set(permissions)) != len(permissions):
            raise HTTPException(422, "INVALID_PERMISSIONS")

    async def role(self, role_id):
        if role_id in ROLES:
            raise HTTPException(409, "SYSTEM_ROLE_IMMUTABLE")
        row = (await self.session.execute(select(AdminResource).where(
            AdminResource.kind == "CUSTOM_ROLE", AdminResource.status == "ACTIVE",
            AdminResource.payload["role_id"].astext == role_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "ROLE_NOT_FOUND")
        return row

    async def unique_name(self, name, exclude=None):
        if any(r["name"].casefold() == name.casefold() and r["id"] != exclude for r in await self.roles()):
            raise HTTPException(409, "ROLE_NAME_EXISTS")

    async def create_role(self, admin, data):
        manager(self.session, admin)
        await security_lock(self.session)
        self.validate_permissions(data.permissions)
        await self.unique_name(data.name)
        rid = uuid.uuid4()
        row = AdminResource(id=rid, actor_id=admin.id, kind="CUSTOM_ROLE", status="ACTIVE",
                            expires_at=datetime(2199, 1, 1, tzinfo=timezone.utc),
                            payload={"role_id": "role_" + rid.hex, "name": data.name,
                                     "permissions": sorted(data.permissions), "version": 1})
        self.session.add(row)
        await self.session.flush()
        await self.audit(admin, "security.roles.create", row.id, {"reason": data.reason})
        return self.role_row(row)

    async def change_role(self, admin, role_id, data, delete=False):
        manager(self.session, admin)
        await security_lock(self.session)
        row = await self.role(role_id)
        if row.payload["version"] != data.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        if delete:
            accounts = (await self.session.execute(select(AdminAccount.id).where(
                AdminAccount.role_ids.contains([role_id]),
            ).limit(1))).first()
            pending = (await self.session.execute(select(AdminResource.id).where(
                AdminResource.kind == "ADMIN_INVITATION", AdminResource.status == "PENDING",
                AdminResource.expires_at > now(),
                AdminResource.payload["role_ids"].contains([role_id]),
            ).limit(1))).first()
            if accounts or pending:
                raise HTTPException(409, "ROLE_IN_USE")
            row.status = "DELETED"
        else:
            if data.name is not None:
                await self.unique_name(data.name, role_id)
            if data.permissions is not None:
                self.validate_permissions(data.permissions)
            row.payload = {**row.payload, **data.model_dump(exclude={"reason", "expected_version"}, exclude_unset=True),
                           "version": row.payload["version"] + 1}
        await self.session.flush()
        await self.audit(admin, "security.roles.delete" if delete else "security.roles.update",
                         row.id, {"reason": data.reason})
        return {"id": role_id, "deleted": True} if delete else self.role_row(row)

    def invitation_row(self, row):
        status = "EXPIRED" if row.status == "PENDING" and row.expires_at <= now() else row.status
        return {"id": row.id, "email": row.payload["email"], "name": row.payload["name"],
                "role_ids": row.payload["role_ids"], "data_scope": row.payload["data_scope"],
                "status": status, "expires_at": row.expires_at, "version": row.payload["version"],
                "delivery_method": "MANUAL", "email_sent": False,
                "created_at": row.created_at}

    async def invitation(self, invitation_id):
        row = (await self.session.execute(select(AdminResource).where(
            AdminResource.kind == "ADMIN_INVITATION", AdminResource.id == invitation_id,
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "INVITATION_NOT_FOUND")
        return row

    async def invitations(self, page, page_size, status=None):
        query = select(AdminResource).where(AdminResource.kind == "ADMIN_INVITATION")
        if status == "EXPIRED":
            query = query.where(AdminResource.status == "PENDING", AdminResource.expires_at <= now())
        elif status == "PENDING":
            query = query.where(AdminResource.status == "PENDING", AdminResource.expires_at > now())
        elif status:
            query = query.where(AdminResource.status == status)
        rows, total = await AdminService(self.session).repo.page(
            query.order_by(AdminResource.created_at.desc(), AdminResource.id), page, page_size)
        return {"items": [self.invitation_row(row) for row in rows], "total": total,
                "page": page, "page_size": page_size, "pages": max(1, (total + page_size - 1)//page_size)}

    async def create_invitation(self, admin, data):
        manager(self.session, admin)
        await security_lock(self.session)
        await self.validate_roles(data.role_ids, data.data_scope)
        email = str(data.email).lower()
        account = (await self.session.execute(select(AdminAccount.id).where(AdminAccount.email == email))).first()
        pending = (await self.session.execute(select(AdminResource.id).where(
            AdminResource.kind == "ADMIN_INVITATION", AdminResource.status == "PENDING",
            AdminResource.expires_at > now(), AdminResource.payload["email"].astext == email,
        ))).first()
        if account or pending:
            raise HTTPException(409, "ACCOUNT_OR_INVITATION_EXISTS")
        raw = secrets.token_urlsafe(48)
        row = AdminResource(id=uuid.uuid4(), actor_id=admin.id, kind="ADMIN_INVITATION", status="PENDING",
                            expires_at=now() + timedelta(hours=24),
                            payload={"email": email, "name": data.name, "role_ids": data.role_ids,
                                     "data_scope": data.data_scope.model_dump(mode="json"),
                                     "proof_hash": hashlib.sha256(raw.encode()).hexdigest(), "version": 1})
        self.session.add(row)
        await self.session.flush()
        await self.audit(admin, "security.invitations.create", row.id, {"reason": data.reason})
        return {**self.invitation_row(row), "invitation_token": raw}

    async def change_invitation(self, admin, invitation_id, data, revoke=False):
        manager(self.session, admin)
        await security_lock(self.session)
        row = await self.invitation(invitation_id)
        if row.payload["version"] != data.expected_version:
            raise HTTPException(409, "VERSION_CONFLICT")
        if row.status != "PENDING":
            raise HTTPException(409, "INVITATION_NOT_PENDING")
        if not revoke and row.updated_at > now() - timedelta(seconds=60):
            raise HTTPException(429, "INVITATION_RESEND_COOLDOWN")
        if not revoke:
            duplicate = (await self.session.execute(select(AdminResource.id).where(
                AdminResource.kind == "ADMIN_INVITATION", AdminResource.id != row.id,
                AdminResource.status == "PENDING", AdminResource.expires_at > now(),
                AdminResource.payload["email"].astext == row.payload["email"],
            ))).first()
            account = (await self.session.execute(select(AdminAccount.id).where(
                AdminAccount.email == row.payload["email"],
            ))).first()
            if duplicate or account:
                raise HTTPException(409, "ACCOUNT_OR_INVITATION_EXISTS")
        raw = secrets.token_urlsafe(48)
        row.payload = {**row.payload, "proof_hash": hashlib.sha256(raw.encode()).hexdigest(),
                       "version": row.payload["version"] + 1}
        row.expires_at = now() + timedelta(hours=24)
        if revoke:
            row.status = "REVOKED"
        await self.session.flush()
        await self.audit(admin, "security.invitations.revoke" if revoke else "security.invitations.resend",
                         row.id, {"reason": data.reason})
        return self.invitation_row(row) if revoke else {**self.invitation_row(row), "invitation_token": raw}

    async def accept(self, data):
        # Single-use proof authorizes only the identity/scope frozen by an operator.
        await security_lock(self.session)
        row = await self.invitation(data.invitation_id)
        proof = hashlib.sha256(data.invitation_token.get_secret_value().encode()).hexdigest()
        if row.status != "PENDING" or row.expires_at <= now() or not hmac.compare_digest(proof, row.payload["proof_hash"]):
            raise HTTPException(400, "INVITATION_INVALID_OR_EXPIRED")
        from app.schemas.admin_security import AdminDataScope
        scope = AdminDataScope.model_validate(row.payload["data_scope"])
        await self.validate_roles(row.payload["role_ids"], scope)
        if (await self.session.execute(select(AdminAccount.id).where(
            AdminAccount.email == row.payload["email"],
        ))).first():
            raise HTTPException(409, "ACCOUNT_ALREADY_EXISTS")
        # Invitations from an operator who lost platform security authority cannot be used.
        issuer = await self.session.get(AdminAccount, row.actor_id)
        if not issuer or not issuer.is_active or "role_ceo" not in issuer.role_ids or issuer.garage_scope is not None:
            raise HTTPException(409, "INVITATION_ISSUER_UNAUTHORIZED")
        account = AdminAccount(id=uuid.uuid4(), email=row.payload["email"], name=row.payload["name"],
                               password_hash=await run_in_threadpool(hash_admin_password, data.password.get_secret_value()),
                               role_ids=list(row.payload["role_ids"]),
                               garage_scope=scope.model_dump(mode="json")["garage_ids"] if scope.type == "GARAGES" else None)
        self.session.add(account)
        row.status = "ACCEPTED"
        row.payload = {**row.payload, "proof_hash": "", "accepted_account_id": str(account.id),
                       "version": row.payload["version"] + 1}
        await self.session.flush()
        await self.audit(issuer, "security.invitations.accept", row.id, {"account_id": str(account.id)})
        return {"account_id": account.id, "invitation_id": row.id, "accepted": True}
