from typing import Annotated, Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
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
async def sign_in(data: SignInRequest, session: DBSession):
    """Sign in with mobile number — sends OTP."""
    service = AuthService(session)
    result = await service.sign_in(data)
    return APIResponse.ok(data=result, message=result["message"])


@router.post("/send-otp", response_model=APIResponse)
async def send_otp(data: SendOTPRequest, session: DBSession):
    """Send a fresh OTP to a registered mobile number."""
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
