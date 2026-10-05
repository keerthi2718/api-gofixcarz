"""Explicit, development-only admin bootstrap. Never called during signup/startup."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.database.session import async_session, engine
from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User, UserRole


async def main():
    import uuid
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=uuid.UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply promotion; omitted means preview only")
    args = parser.parse_args()
    if make_url(settings.DATABASE_URL).host != "helium":
        raise SystemExit("Refusing changes: this command is only for the internal development database.")
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == args.user_id, User.deleted_at.is_(None)).with_for_update()
        )).scalar_one_or_none()
        if not user or not user.is_active:
            raise SystemExit("An existing active user is required.")
        if user.role == UserRole.ADMIN.value:
            print("This account already has the admin role.")
            return
        if not args.apply:
            print("Preview: this account would gain platform-wide admin access. Add --apply to confirm.")
            return
        user.role = UserRole.ADMIN.value
        session.add(AdminAuditLog(
            actor_id=user.id, action="role.bootstrap", resource_id=user.id,
            details={"source": "trusted_development_operator", "role": "admin"},
        ))
        await session.commit()
        print("Development account promoted. Sign in again to receive a JWT showing the admin role.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.run(engine.dispose())
