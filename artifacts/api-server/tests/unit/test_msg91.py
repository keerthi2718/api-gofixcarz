"""OTP submission checks: no real SMS, database, or credentials needed."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from loguru import logger

from app.core.exceptions import AppException
from app.schemas.auth import SendOTPRequest, SignInRequest, SignUpRequest
from app.services.auth_service import AuthService
from app.utils import msg91


REQUEST_ID = "366a646975706e6e36476778"


def mock_gateway(monkeypatch, handler):
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        msg91.httpx, "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.parametrize("body", [
    {"type": "success", "message": REQUEST_ID},
    REQUEST_ID,
])
async def test_accepted_request(monkeypatch, body):
    def handler(request):
        assert request.url.params["response"] == "json"
        assert request.url.params["message"] == (
            "Your Skill Wallet platform account activation OTP is 123456"
        )
        if isinstance(body, dict):
            return httpx.Response(200, json=body)
        return httpx.Response(200, text=body)
    mock_gateway(monkeypatch, handler)
    assert await msg91.send_otp_sms("910000000000", "123456") is True


@pytest.mark.parametrize("body", [
    {"type": "error", "message": "Invalid auth key", "code": "101"},
    {"type": "success", "message": ""},
    {"message": REQUEST_ID},
    ["success"],
    "101",
    "<html>upstream error</html>",
])
async def test_http_200_is_not_enough(monkeypatch, body):
    mock_gateway(monkeypatch, lambda request: (
        httpx.Response(200, text=body) if isinstance(body, str)
        else httpx.Response(200, json=body)
    ))
    assert await msg91.send_otp_sms("910000000000", "123456") is False


@pytest.mark.parametrize("failure", ["http", "timeout"])
async def test_transport_failure_does_not_leak_secrets(monkeypatch, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-auth-key otp=123456", request=request)
        return httpx.Response(401)
    mock_gateway(monkeypatch, handler)
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        assert await msg91.send_otp_sms("910000000000", "123456") is False
    finally:
        logger.remove(sink)
    output = "".join(messages)
    assert "910000000000" not in output
    assert "123456" not in output
    assert "secret-auth-key" not in output
    assert "https://" not in output


@pytest.mark.parametrize("method,schema", [
    ("sign_in", SignInRequest),
    ("send_otp", SendOTPRequest),
])
@pytest.mark.parametrize("accepted", [True, False])
async def test_auth_respects_sms_result(monkeypatch, method, schema, accepted):
    service = AuthService(AsyncMock())
    service.user_repo = AsyncMock()
    service.user_repo.get_by_mobile.return_value = SimpleNamespace(
        mobile="0000000000", country_code="91", is_active=True,
    )
    sms = AsyncMock(return_value=accepted)
    monkeypatch.setattr("app.services.auth_service.send_otp_sms", sms)
    if accepted:
        result = await getattr(service, method)(schema(mobile="0000000000"))
        assert "OTP sent" in result["message"]
    else:
        with pytest.raises(AppException) as error:
            await getattr(service, method)(schema(mobile="0000000000"))
        assert error.value.status_code == 503
        assert "could not accept" in error.value.message
    sms.assert_awaited_once()


async def test_signup_failure_explains_account_already_created(monkeypatch):
    service = AuthService(AsyncMock())
    service.user_repo = AsyncMock()
    service.garage_repo = AsyncMock()
    service.user_repo.get_by_mobile.return_value = None
    service.user_repo.get_by_email.return_value = None
    service.user_repo.create.return_value = SimpleNamespace(id="test-user")
    monkeypatch.setattr(
        "app.services.auth_service.send_otp_sms", AsyncMock(return_value=False),
    )
    with pytest.raises(AppException) as error:
        await service.sign_up(SignUpRequest(
            first_name="Test", workshop_name="Test Garage",
            email="test@example.com", mobile="0000000000", terms_accepted=True,
        ))
    assert error.value.status_code == 503
    assert "Account created" in error.value.message
    service.garage_repo.create.assert_awaited_once()