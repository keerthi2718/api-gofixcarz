"""Explicit dedicated development admin setup; secret values never leave runtime."""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import TypeAdapter, EmailStr
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.admin_security import hash_admin_password, verify_admin_password
from app.core.config import settings
from app.database.session import async_session, engine
from app.models.admin_account import AdminAccount
from app.models.admin_audit_log import AdminAuditLog


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email keerthana@thesmartbridge.com", required=True)
    parser.add_argument("--name", default="Platform administrator")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if make_url(settings.DATABASE_URL).host != "helium":
        raise SystemExit("Refusing changes outside the internal development database.")
    email = str(TypeAdapter(EmailStr).validate_python(args.email)).strip().lower()
    if not args.apply:
        print("Preview: a separate development admin account would be created. Use --apply to confirm.")
        return
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "")
    if not 16 <= len(password) <= 128:
        raise SystemExit("Set ADMIN_BOOTSTRAP_PASSWORD securely to a password of 16 to 128 characters.")
    async with async_session() as session:
        existing = (await session.execute(select(AdminAccount).where(
            AdminAccount.email == email,
        ))).scalar_one_or_none()
        if existing:
            # Idempotent re-runs must never silently overwrite credentials.
            if existing.is_active and verify_admin_password(password, existing.password_hash):
                print("Development admin already exists; password verification succeeded.")
                return
            raise SystemExit("Admin account already exists; refusing to overwrite its credentials.")
        account = AdminAccount(email=email, name=args.name, password_hash=hash_admin_password(password),
                               role_ids=["role_ceo"], garage_scope=None)
        session.add(account)
        await session.flush()
        session.add(AdminAuditLog(
            admin_account_id=account.id, action="account.bootstrap", resource_id=account.id,
            details={"source": "trusted_development_operator"},
        ))
        await session.commit()
        if not verify_admin_password(password, account.password_hash):
            raise SystemExit("Credential verification failed.")
        print("Development admin created; password hash verification succeeded. No SMS was sent.")


if __name__ == "__main__":
    async def run():
        try:
            await main()
        finally:
            await engine.dispose()
    asyncio.run(run())
