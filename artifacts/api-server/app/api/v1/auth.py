from typing import Annotated, Optional
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.core.config import settings
from app.services.sms_delivery_service import SMSDeliveryService, normalize_report

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


def _require_delivery_token(request: Request, *, diagnostics: bool = False) -> None:
    configured = (
        settings.MSG91_DIAGNOSTICS_TOKEN if diagnostics else settings.MSG91_WEBHOOK_TOKEN
    ).get_secret_value()
    header = "X-SMS-Diagnostics-Token" if diagnostics else "X-MSG91-Webhook-Token"
    if len(configured) < 32:
        raise HTTPException(503, "Delivery tracking authentication is not configured")
    supplied = request.headers.get(header, "")
    if not hmac.compare_digest(supplied.encode(), configured.encode()):
        raise HTTPException(401, "Invalid delivery tracking authentication")


@router.post("/msg91/delivery-report", response_model=APIResponse)
async def msg91_delivery_report(request: Request, session: DBSession):
    """Authenticated OTP/SMS On Report Received, configured for flat JSON."""
    _require_delivery_token(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "JSON delivery report required")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            raise HTTPException(413, "Delivery report too large")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Invalid delivery report") from None
    report = normalize_report(payload)
    await SMSDeliveryService(session).record_report(report)
    return APIResponse.ok(data={"received": True}, message="Delivery report received")


@router.get("/msg91/delivery-status/{request_id}", response_model=APIResponse)
async def msg91_delivery_status(request_id: str, request: Request, session: DBSession):
    """Operations-only status; never expose phone, user, OTP or raw provider text."""
    _require_delivery_token(request, diagnostics=True)
    result = await SMSDeliveryService(session).diagnostic(request_id)
    return APIResponse.ok(data=result, message="SMS delivery status")


def _mobile_key(request: Request) -> str:
    """Rate-limit key for /send-otp — keyed on the 'mobile' field."""
    body: dict = getattr(request.state, "_body_json", {})
    mobile: str = str(body.get("mobile", "")).strip()
    if mobile:
        return f"mobile:{mobile}"
    return get_remote_address(request)


def _login_key(request: Request) -> str:
    """Rate-limit key for /sign-in — keyed on the 'mobile' field.

    The OTPBodyCacheMiddleware (registered in main.py) pre-reads and parses
    the JSON body onto request.state._body_json before slowapi evaluates this
    function. The value is normalised (stripped) so that whitespace variants
    share the same bucket and cannot bypass the limit.
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
@limiter.limit("5/minute", key_func=_login_key)
async def sign_in(request: Request, data: SignInRequest, session: DBSession):
    """Sign in with mobile number — sends OTP. Rate-limited to 5/min per mobile."""
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
