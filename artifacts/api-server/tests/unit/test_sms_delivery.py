"""No SMS sent. Callbacks use fake credentials and mocked DB sessions."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql

from app.api.v1.auth import router
from app.core.config import settings
from app.database.session import get_session
from app.services.sms_delivery_service import SMSDeliveryService, normalize_report

ID = "366a646975706e6e36476778"
OTHER_ID = "466a646975706e6e36476778"
TOKEN = "fake-webhook-token-only-for-tests-12345"
DIAG_TOKEN = "fake-diagnostic-token-only-for-tests-67890"
CALLBACK = "/auth/msg91/delivery-report"
DIAGNOSTIC = f"/auth/msg91/delivery-status/{ID}"


@pytest.fixture
async def api(monkeypatch):
    monkeypatch.setattr(settings, "MSG91_WEBHOOK_TOKEN", SecretStr(TOKEN))
    monkeypatch.setattr(settings, "MSG91_DIAGNOSTICS_TOKEN", SecretStr(DIAG_TOKEN))
    session = AsyncMock()
    app = FastAPI()
    app.include_router(router, prefix="/auth")

    async def fake_session():
        yield session

    app.dependency_overrides[get_session] = fake_session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client, session


@pytest.mark.parametrize("token", [None, "", "wrong", DIAG_TOKEN, "é" * 32])
async def test_callback_authentication_before_body_or_db(api, token):
    client, session = api
    # httpx headers are ASCII, so supply raw UTF-8 bytes for the unusual case.
    headers = {"X-MSG91-Webhook-Token": token.encode()} if token is not None else {}
    response = await client.post(CALLBACK, content=b"bad-json secret-otp", headers=headers)
    assert response.status_code == 401
    assert "secret-otp" not in response.text
    session.execute.assert_not_awaited()


async def test_disabled_callback_fails_closed(api, monkeypatch):
    client, session = api
    monkeypatch.setattr(settings, "MSG91_WEBHOOK_TOKEN", SecretStr(""))
    response = await client.post(CALLBACK, json={"requestId": ID, "status": "1"})
    assert response.status_code == 503
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("payload", [
    None, [], {}, {"requestId": ID}, {"requestId": ID, "status": True},
    {"requestId": ID, "status": "99"},
    {"requestId": ID, "status": "DELIVERED"},
    {"requestId": "phone=910000000000 otp=123456", "status": "1"},
    {"requestId": ID, "status": ["1"]},
])
async def test_invalid_callback_is_redacted(api, payload):
    client, session = api
    response = await client.post(
        CALLBACK, content=json.dumps(payload), headers={
            "X-MSG91-Webhook-Token": TOKEN, "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
    assert "123456" not in response.text
    assert "910000000000" not in response.text
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("content,content_type,code", [
    (b"not json otp=123456", "application/json", 400),
    (b"\xff", "application/json", 400),
    (b"x" * 8193, "application/json", 413),
    (b"{}", "application/x-www-form-urlencoded", 415),
])
async def test_callback_body_limits(api, content, content_type, code):
    client, session = api
    response = await client.post(CALLBACK, content=content, headers={
        "X-MSG91-Webhook-Token": TOKEN, "Content-Type": content_type,
    })
    assert response.status_code == code
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("status,expected,category", [
    ("0", "pending", None), (1, "delivered", None),
    ("2", "failed", "operator_failure"), ("9", "failed", "ndnc"),
    ("16", "failed", "rejected"), ("25", "failed", "rejected"),
    ("17", "failed", "blocked_number"), ("20", "failed", "country_blocked"),
])
def test_documented_status_mapping(status, expected, category):
    assert normalize_report({"requestId": ID, "status": status}) == {
        "request_id": ID, "status": expected, "failure_category": category,
    }


async def test_callback_correlates_and_discards_personal_data(api):
    client, session = api
    response = await client.post(CALLBACK, json={
        "requestId": ID, "status": "2",
        "failureReason": "phone=910000000000 otp=123456 authkey=secret",
        "telNum": "910000000000", "message": "OTP 123456",
    }, headers={"X-MSG91-Webhook-Token": TOKEN})
    assert response.status_code == 200
    stmt = session.execute.call_args.args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert compiled.params["request_id"] == ID
    assert compiled.params["status"] == "failed"
    assert compiled.params["failure_category"] == "operator_failure"
    for secret in ["910000000000", "123456", "authkey", "secret"]:
        assert secret not in str(compiled.params)
        assert secret not in response.text
    assert "ON CONFLICT" in str(compiled)


def test_only_exact_safe_reasons_survive():
    assert normalize_report({
        "requestId": ID, "status": "16",
        "failureReason": "Template Id not found on DLT",
    })["failure_category"] == "dlt_template_not_found"
    assert normalize_report({
        "requestId": ID, "status": "16",
        "failureReason": "Template Id not found on DLT phone=910000000000",
    })["failure_category"] == "rejected"


@pytest.mark.parametrize("token,code", [(None, 401), (TOKEN, 401), (DIAG_TOKEN, 200)])
@pytest.mark.parametrize("delivery_status", ["pending", "delivered", "failed"])
async def test_diagnostics_require_separate_operations_token(api, token, code, delivery_status):
    client, session = api
    record = SimpleNamespace(
        request_id=ID, status=delivery_status, failure_category=None,
        accepted_at=datetime.now(timezone.utc), reported_at=None,
    )
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=record))
    response = await client.get(
        DIAGNOSTIC, headers={"X-SMS-Diagnostics-Token": token} if token else {},
    )
    assert response.status_code == code
    if code == 200:
        assert response.json()["data"]["status"] == delivery_status
        query = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        assert ID in query.params.values()
        assert "accepted_at IS NOT NULL" in str(query)
        assert set(response.json()["data"]) == {
            "request_id", "status", "failure_category", "accepted_at", "reported_at",
        }
    else:
        session.execute.assert_not_awaited()


async def test_disabled_diagnostics_fail_closed(api, monkeypatch):
    client, session = api
    monkeypatch.setattr(settings, "MSG91_DIAGNOSTICS_TOKEN", SecretStr("too-short"))
    response = await client.get(
        DIAGNOSTIC, headers={"X-SMS-Diagnostics-Token": DIAG_TOKEN},
    )
    assert response.status_code == 503
    session.execute.assert_not_awaited()


async def test_unknown_submission_is_not_publicly_enumerable(api):
    client, session = api
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    response = await client.get(
        DIAGNOSTIC, headers={"X-SMS-Diagnostics-Token": DIAG_TOKEN},
    )
    assert response.status_code == 404


async def test_database_correlation_retries_and_early_reports():
    """Use a temporary Postgres table, never modify real application records."""
    from sqlalchemy import MetaData
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool
    from sqlalchemy.schema import CreateTable
    from app.database.session import _db_url, _connect_args
    from app.models.sms_delivery import SMSDelivery

    engine = create_async_engine(_db_url, connect_args=_connect_args, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            table = SMSDelivery.__table__.to_metadata(MetaData())
            table._prefixes = ["TEMPORARY"]
            await connection.execute(CreateTable(table))
            session = AsyncSession(bind=connection, expire_on_commit=False)
            async with session:
                service = SMSDeliveryService(session)
                await service.register_submission(ID)
                assert (await service.diagnostic(ID))["status"] == "pending"
                failed = normalize_report({"requestId": ID, "status": "16"})
                await service.record_report(failed)
                original = await service.diagnostic(ID)
                await service.record_report(failed)
                assert await service.diagnostic(ID) == original
                await service.record_report(normalize_report({"requestId": ID, "status": "0"}))
                assert (await service.diagnostic(ID))["status"] == "failed"
                delivered = normalize_report({"requestId": ID, "status": "1"})
                await service.record_report(delivered)
                await service.record_report(failed)
                current = await service.diagnostic(ID)
                assert current["status"] == "delivered"
                assert current["failure_category"] is None

                await service.record_report(normalize_report({"requestId": OTHER_ID, "status": "1"}))
                with pytest.raises(HTTPException) as exc:
                    await service.diagnostic(OTHER_ID)
                assert exc.value.status_code == 404
                await service.register_submission(OTHER_ID)
                assert (await service.diagnostic(OTHER_ID))["status"] == "delivered"
                assert (await service.diagnostic(ID))["request_id"] == ID
                # Remove only the isolated table before returning the connection.
                await connection.exec_driver_sql("DROP TABLE pg_temp.sms_deliveries")
    finally:
        await engine.dispose()