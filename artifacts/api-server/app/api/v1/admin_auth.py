"""Private admin authentication contract, excluded from public OpenAPI."""
from typing import Annotated
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import decode_admin_access
from app.core.exceptions import UnauthorizedException
from app.database.session import get_session
from app.dependencies.auth import CurrentAdmin
from app.models.admin_account import AdminAccount, AdminSession
from app.schemas.admin_auth import AdminLoginRequest, AdminRefreshRequest
from app.schemas.response import APIResponse
from app.services.admin_auth_service import AdminAuthService

router = APIRouter(include_in_schema=False)
limiter = Limiter(key_func=get_remote_address)
DBSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("/sign-in")
@limiter.limit("5/minute")
async def sign_in(request: Request, data: AdminLoginRequest, session: DBSession):
    result = await AdminAuthService(session).login(str(data.email), data.password.get_secret_value())
    if result is None:
        return JSONResponse(status_code=401, content={
            "success": False, "message": "Invalid credentials or account unavailable.",
            "data": None, "errors": [], "status_code": 401,
        }, headers={"Cache-Control": "no-store"})
    return JSONResponse(content=APIResponse.ok(data=result).model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh(request: Request, data: AdminRefreshRequest, session: DBSession):
    result = await AdminAuthService(session).refresh(data.refresh_token.get_secret_value())
    return JSONResponse(content=APIResponse.ok(data=result).model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})


@router.post("/logout")
async def logout(request: Request, admin: CurrentAdmin, session: DBSession):
    if not isinstance(admin, AdminAccount):
        raise UnauthorizedException("A dedicated admin session is required.")
    payload = decode_admin_access(request.headers.get("authorization", "").split(" ", 1)[-1])
    login_session = await session.get(AdminSession, uuid.UUID(payload["sid"]))
    login_session.revoked_at = datetime.now(timezone.utc)
    AdminAuthService(session).audit(admin, "auth.logout")
    return APIResponse.ok(data={"logged_out": True})
