import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_access_token
from app.core.admin_security import decode_admin_access
from app.models.admin_account import AdminAccount, AdminSession
from app.database.session import get_session
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if not credentials:
        raise UnauthorizedException("Authentication required.")
    token = credentials.credentials
    user_id = decode_access_token(token)
    if not user_id:
        raise UnauthorizedException("Invalid or expired token.")
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise UnauthorizedException("Invalid token payload.")
    repo = UserRepository(session)
    user = await repo.get_by_id(uid)
    if not user:
        raise UnauthorizedException("User not found.")
    if not user.is_active:
        raise UnauthorizedException("Account is inactive.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DBSession = Annotated[AsyncSession, Depends(get_session)]


async def get_admin_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | AdminAccount:
    if credentials:
        payload = decode_admin_access(credentials.credentials)
        if payload:
            from datetime import datetime, timezone
            try:
                account_id, sid = uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
            except (ValueError, TypeError, KeyError):
                raise UnauthorizedException("Invalid token payload.")
            account = await session.get(AdminAccount, account_id)
            login_session = await session.get(AdminSession, sid)
            if (
                not account or not account.is_active or not login_session
                or login_session.admin_account_id != account.id
                or login_session.revoked_at is not None
                or login_session.expires_at <= datetime.now(timezone.utc)
                or payload["ver"] != account.credential_version
                or login_session.credential_version != account.credential_version
            ):
                raise UnauthorizedException("Invalid or expired session.")
            return account
    # Existing explicitly promoted OTP administrators retain their current flow.
    return await get_current_user(credentials, session)


async def get_current_admin(
    current_user: Annotated[User | AdminAccount, Depends(get_admin_principal)],
) -> User | AdminAccount:
    """Database role is authoritative, never the client's cached JWT role."""
    if current_user.role != UserRole.ADMIN.value:
        raise ForbiddenException("Admin access required.")
    return current_user


CurrentAdmin = Annotated[User | AdminAccount, Depends(get_current_admin)]
