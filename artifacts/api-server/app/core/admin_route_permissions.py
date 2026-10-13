"""One server-side permission gate shared by old and new admin routers."""
from app.core.admin_policy import require_permission


def enforce_route_permission(request, session, legacy=False):
    path = request.url.path.split("/api/v1/admin", 1)[-1].strip("/")
    method = request.method
    if path == "-auth/logout":
        return
    if path in ("me", "menus") or path.startswith("/") or not path:
        return
    root = path.split("/")[0]
    permission = {
        "dashboard": "dashboard.read", "analytics": "dashboard.read",
        "users": "users.read", "garage-owners": "garages.read", "garages": "garages.read",
        "bookings": "bookings.read", "jobs": "jobs.read", "alerts": "jobs.read",
        "billing": "finance.read", "audit-logs": "audit.read", "activity": "activity.read",
        "permissions": "security.read", "roles": "security.read", "staff": "security.read",
        "customers": "customers.read", "finance": "finance.read", "invoices": "finance.read",
        "payments": "finance.read", "refunds": "finance.read", "disputes": "finance.read",
        "notifications": "notifications.read", "announcements": "notifications.read",
        "support": "support.read", "garage-owner-statistics": "owner_statistics.read",
        "reports": "reports.export",
    }.get(root)
    if method not in ("GET", "HEAD"):
        if root == "staff":
            permission = "security.manage"
        elif root == "users":
            permission = "users.status.write"
        elif root == "garages":
            permission = "garages.verify" if path.endswith("/verification") else "garages.status.write"
        elif root == "announcements":
            permission = "announcements.send"
        elif root == "support":
            permission = ("support.assign" if path.endswith("/assignment") else
                          "support.reply" if path.endswith("/messages") else "support.manage")
    if permission:
        require_permission(session, permission, recent_mfa=method not in ("GET", "HEAD") and not legacy)
    else:
        from fastapi import HTTPException
        raise HTTPException(403, "UNMAPPED_ADMIN_OPERATION")
    if root == "activity":
        require_permission(session, "bookings.read")
        require_permission(session, "jobs.read")
