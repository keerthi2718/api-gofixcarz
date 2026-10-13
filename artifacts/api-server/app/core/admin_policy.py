"""Configurable development policies, not production sign-off."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.config import settings

PERMISSIONS = {
    "security.read", "security.manage", "dashboard.read", "users.read", "users.status.write",
    "garages.read", "garages.status.write", "garages.verify", "customers.read",
    "bookings.read", "jobs.read", "finance.read", "notifications.read", "announcements.send",
    "support.read", "support.assign", "support.manage", "support.reply",
    "owner_statistics.read", "reports.export", "audit.read", "activity.read",
}
ROLES = {
    "role_ceo": sorted(PERMISSIONS),
    "role_operations": [
        "dashboard.read", "garages.read", "garages.status.write", "garages.verify",
        "customers.read", "bookings.read", "jobs.read", "notifications.read",
        "announcements.send", "support.read", "support.assign", "support.manage",
        "support.reply", "owner_statistics.read", "activity.read", "reports.export",
    ],
    "role_finance": [
        "dashboard.read", "garages.read", "finance.read", "owner_statistics.read", "reports.export",
    ],
    "role_support": [
        "garages.read", "customers.read", "bookings.read", "jobs.read", "notifications.read",
        "support.read", "support.assign", "support.reply", "activity.read",
    ],
}


def effective_permissions(account):
    return set().union(*(set(ROLES.get(role, [])) for role in account.role_ids))


def require_permission(session, permission, *, recent_mfa=False):
    access = session.info.get("admin_access")
    if not access or permission not in access["permissions"]:
        raise HTTPException(403, "PERMISSION_DENIED")
    if recent_mfa and settings.ADMIN_MFA_REQUIRED:
        stamp = access.get("mfa_verified_at")
        if not stamp or stamp < datetime.now(timezone.utc) - timedelta(minutes=5):
            raise HTTPException(403, "RECENT_MFA_REQUIRED")
    return access


def scope_ids(session):
    access = session.info.get("admin_access")
    return access.get("garage_ids") if access else None


def constrain_garages(query, session, garage_column):
    ids = scope_ids(session)
    if ids is not None:
        query = query.where(garage_column.in_(ids))
    return query
