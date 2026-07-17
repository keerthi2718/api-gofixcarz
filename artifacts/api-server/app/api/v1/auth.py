from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.dependencies.auth import CurrentUser
from app.schemas.auth import (
    LogoutRequest,
    RefreshRequest,
    SendOTPRequest,
    SignInRequest,
    SignUpRequest,
    VerifyOTPRequest,
)
from app.schemas.response import APIResponse
from app.services.auth_service import AuthService

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


def _mobile_key(request: Request) -> str:
    """Sync rate-limit key based on mobile number.

    The OTPBodyCacheMiddleware (registered in main.py) pre-reads and parses
    the JSON body onto request.state._body_json for OTP routes before slowapi
    evaluates this function. Falls back to client IP if the field is absent.

    Mobile is normalized identically to the Pydantic schema validators (strip
    whitespace) so that semantically equivalent numbers share a single bucket
    and cannot bypass the limit by varying leading/trailing spaces.
    """
    body: dict = getattr(request.state, "_body_json", {})
    mobile: str = str(body.get("mobile", "")).strip()
    if mobile:
        return f"mobile:{mobile}"
    return get_remote_address(request)


limiter = Limiter(key_func=get_remote_address)


@router.post("/sign-up", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(data: SignUpRequest, session: DBSession):
    """Register a new user and send OTP."""
    service = AuthService(session)
    result = await service.sign_up(data)
    return JSONResponse(
        status_code=201,
        content=APIResponse.created(data=result, message=result["message"]).model_dump(),
    )


@router.post("/sign-in", response_model=APIResponse)
@limiter.limit("5/minute", key_func=_mobile_key)
async def sign_in(request: Request, data: SignInRequest, session: DBSession):
    """Sign in with mobile number — sends OTP. Rate-limited to 5/min per mobile number."""
    service = AuthService(session)
    result = await service.sign_in(data)
    return APIResponse.ok(data=result, message=result["message"])


@router.post("/send-otp", response_model=APIResponse)
@limiter.limit("5/minute", key_func=_mobile_key)
async def send_otp(request: Request, data: SendOTPRequest, session: DBSession):
    """Send a fresh OTP to a registered mobile number. Rate-limited to 5/min per mobile number."""
    service = AuthService(session)
    result = await service.send_otp(data)
    return APIResponse.ok(data=result, message=result["message"])


@router.post("/verify-otp", response_model=APIResponse)
async def verify_otp(data: VerifyOTPRequest, session: DBSession):
    """Verify OTP and receive a JWT access token + refresh token."""
    service = AuthService(session)
    token_response = await service.verify_otp(data)
    return APIResponse.ok(
        data=token_response.model_dump(),
        message="OTP verified successfully. You are now logged in.",
    )


@router.post("/refresh", response_model=APIResponse)
async def refresh_token(data: RefreshRequest, session: DBSession):
    """Exchange a valid refresh token for a new access token and rotated refresh token."""
    service = AuthService(session)
    token_response = await service.refresh(data.refresh_token)
    return APIResponse.ok(
        data=token_response.model_dump(),
        message="Token refreshed successfully.",
    )


@router.post("/logout", response_model=APIResponse)
async def logout(current_user: CurrentUser, data: LogoutRequest, session: DBSession):
    """Logout the current user — revokes the provided refresh token (or all sessions)."""
    service = AuthService(session)
    result = await service.logout(str(current_user.id), data.refresh_token)
    return APIResponse.ok(data=result, message=result["message"])
