"""Customer-only authentication and profile endpoints, phase one."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.customer_security import now
from app.database.session import get_session
from app.schemas.customer_app import (
    ChallengeRequest, ChallengeResponse, ContactChangeRequest, ContactResponse,
    LoginOTPRequest, LoginVerifyRequest, LogoutResponse, ProfilePatch,
    ProfileResponse, RefreshRequest, RegisterRequest, SessionResponse, TokenResponse,
    VerifyRequest,
)
from app.schemas.response import APIResponse
from app.services.customer_auth_service import CustomerAuthService
from app.services.customer_otp_service import fail

router = APIRouter(
    prefix="/customer-app", tags=["Customer App"],
    responses={
        code: {"model": APIResponse, "description": description}
        for code, description in {
            400: "Invalid, expired or consumed OTP/challenge.",
            401: "Missing credentials, invalid token or revoked/expired session.",
            403: "Recent OTP authentication is required for contact changes.",
            409: "Verified mobile number is already registered.",
            422: "Invalid fields, unsupported email channel or terms version.",
            429: "OTP attempt limit, resend cooldown or durable abuse limit exceeded.",
            503: "SMS provider did not accept the OTP submission.",
        }.items()
    },
)
DB = Annotated[AsyncSession, Depends(get_session)]
bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


async def service(request: Request, response: Response, db: DB):
    response.headers["Cache-Control"] = "no-store"
    return CustomerAuthService(db, request)


Service = Annotated[CustomerAuthService, Depends(service)]


async def principal(svc: Service, credentials: Credentials):
    if not credentials:
        fail("AUTH_REQUIRED", 401)
    return await svc.principal(credentials.credentials)


Principal = Annotated[tuple, Depends(principal)]


@router.post("/auth/register", response_model=APIResponse[ChallengeResponse], status_code=202)
async def register(data: RegisterRequest, svc: Service):
    result = await svc.start(data.identifier, "REGISTER", registration={
        "name": data.name, "terms_version": data.terms_version,
    })
    return APIResponse.ok(result, "OTP submission accepted; delivery is not guaranteed.", 202)


@router.post("/auth/otp/send", response_model=APIResponse[ChallengeResponse], status_code=202)
async def send(data: LoginOTPRequest, svc: Service):
    return APIResponse.ok(await svc.login(data), "OTP submission accepted.", 202)


@router.post(
    "/auth/otp/resend", response_model=APIResponse[ChallengeResponse], status_code=202,
    openapi_extra={"security": [{}, {"HTTPBearer": []}]},
)
async def resend(data: ChallengeRequest, svc: Service, credentials: Credentials):
    who = await svc.principal(credentials.credentials) if credentials else None
    return APIResponse.ok(await svc.resend(data.challenge_id, who), "OTP submission accepted.", 202)


@router.post("/auth/otp/verify", response_model=APIResponse[TokenResponse])
async def verify(data: LoginVerifyRequest, svc: Service):
    return APIResponse.ok(await svc.complete_login(data), "Customer authenticated.")


@router.post("/auth/refresh", response_model=APIResponse[TokenResponse])
async def refresh(data: RefreshRequest, svc: Service):
    return APIResponse.ok(await svc.refresh(data.refresh_token))


@router.get("/auth/session", response_model=APIResponse[SessionResponse])
async def session(who: Principal):
    from datetime import datetime, timezone
    return APIResponse.ok({
        "session_id": who[2].id, "customer_id": who[0].id, "authenticated": True,
        "expires_at": datetime.fromtimestamp(who[3]["exp"], timezone.utc),
    })


@router.post("/auth/logout", response_model=APIResponse[LogoutResponse])
async def logout(svc: Service, credentials: Credentials):
    if not credentials:
        fail("AUTH_REQUIRED", 401)
    who = await svc.principal(credentials.credentials, allow_revoked=True)
    if who[2].revoked_at is None:
        who[2].revoked_at = now()
    from sqlalchemy import update
    from app.models.customer_workspace import CustomerResource
    await svc.db.execute(update(CustomerResource).where(
        CustomerResource.customer_id == who[0].id, CustomerResource.kind == "DEVICE",
        CustomerResource.payload["session_id"].astext == str(who[2].id)
    ).values(status="DETACHED", payload={}))
    return APIResponse.ok({"logged_out": True})


@router.get("/me", response_model=APIResponse[ProfileResponse])
async def me(svc: Service, who: Principal):
    return APIResponse.ok(await svc.profile_with_photo(*who[:2]))


@router.patch("/me", response_model=APIResponse[ProfileResponse])
async def patch(data: ProfilePatch, svc: Service, who: Principal):
    return APIResponse.ok(await svc.update_profile(data, who))


@router.post("/me/contact-change", response_model=APIResponse[ChallengeResponse], status_code=202)
async def contact_change(data: ContactChangeRequest, svc: Service, who: Principal):
    return APIResponse.ok(await svc.start_contact_change(data, who), "OTP submission accepted.", 202)


@router.post("/me/contact-change/verify", response_model=APIResponse[ContactResponse])
async def verify_contact(data: VerifyRequest, svc: Service, who: Principal):
    return APIResponse.ok(await svc.complete_contact_change(data, who))
