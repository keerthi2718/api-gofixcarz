import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_access_token
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


async def get_current_admin(current_user: CurrentUser) -> User:
    """Database role is authoritative, never the client's cached JWT role."""
    if current_user.role != UserRole.ADMIN.value:
        raise ForbiddenException("Admin access required.")
    return current_user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
