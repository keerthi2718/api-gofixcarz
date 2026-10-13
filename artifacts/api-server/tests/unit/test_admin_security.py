from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from jose import jwt
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import create_access_token, decode_access_token
from app.dependencies.auth import get_current_admin
from app.schemas.admin import AdminUserStatusUpdate
from app.schemas.auth import SendOTPRequest, SignUpRequest, VerifyOTPRequest
from app.schemas.profile import ProfileUpdate
from app.services.auth_service import AuthService


def test_role_is_in_signed_access_token():
    uid = str(uuid4())
    token = create_access_token(uid, role="admin")
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["role"] == "admin"
    assert payload["type"] == "access"
    assert decode_access_token(token) == uid


def test_default_role_is_garage_owner():
    payload = jwt.decode(
        create_access_token(uuid4()), settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
    )
    assert payload["role"] == "garage_owner"


@pytest.mark.parametrize("payload", [
    {"sub": str(uuid4()), "type": "refresh", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
    {"sub": str(uuid4()), "type": "access"},
    {"sub": "", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
])
def test_non_access_or_incomplete_tokens_denied(payload):
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert decode_access_token(token) is None


def test_expired_and_malformed_jwt_denied():
    assert decode_access_token(create_access_token(uuid4(), timedelta(seconds=-1))) is None
    assert decode_access_token("not.a.jwt") is None


async def test_current_database_role_controls_admin_access():
    from starlette.requests import Request
    admin = SimpleNamespace(role="admin", id=uuid4())
    session = SimpleNamespace(info={})
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/admin/me", "headers": []})
    assert await get_current_admin(admin, session, request) is admin
    admin.role = "garage_owner"
    with pytest.raises(ForbiddenException):
        await get_current_admin(admin, session, request)


@pytest.mark.parametrize("schema,data", [
    (SignUpRequest, {"role": "admin"}),
    (SignUpRequest, {"is_active": True}),
    (ProfileUpdate, {"role": "admin"}),
    (ProfileUpdate, {"is_active": True}),
    (AdminUserStatusUpdate, {"is_active": True, "role": "admin"}),
    (AdminUserStatusUpdate, {"is_active": "false"}),
])
def test_public_schemas_cannot_grant_privileges(schema, data):
    with pytest.raises(ValidationError):
        schema.model_validate(data)


@pytest.mark.parametrize("method,data", [
    ("send_otp", SendOTPRequest(mobile="9000000000")),
    ("verify_otp", VerifyOTPRequest(mobile="9000000000", otp="123456")),
])
async def test_inactive_users_cannot_request_otp_or_receive_tokens(method, data):
    service = AuthService(SimpleNamespace())
    service.user_repo.get_by_mobile = AsyncMock(return_value=SimpleNamespace(is_active=False))
    service._submit_otp = AsyncMock()
    with pytest.raises(UnauthorizedException):
        await getattr(service, method)(data)
    service._submit_otp.assert_not_awaited()
