"""First-admin setup authorization and password contract; no real secrets."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings, settings
from app.core.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.schemas.admin_auth import AdminSignupRequest
from app.services.admin_signup_service import AdminSignupService, authorize_admin_setup

KEY = "fixture-only-admin-setup-key-long-enough"
PASSWORD = "fixture-only-long-admin-password"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SIGNUP_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_SETUP_KEY", SecretStr(KEY))


def body():
    return AdminSignupRequest(email="First.Admin@EXAMPLE.com", name=" First admin ", password=PASSWORD)


def test_default_is_disabled():
    assert Settings.model_fields["ADMIN_SIGNUP_ENABLED"].default is False
    assert Settings.model_fields["ADMIN_SETUP_KEY"].default.get_secret_value() == ""


@pytest.mark.parametrize("configured", ["", "x" * 31, "x" * 257])
def test_invalid_configuration_fails_closed(enabled, monkeypatch, configured):
    monkeypatch.setattr(settings, "ADMIN_SETUP_KEY", SecretStr(configured))
    with pytest.raises(NotFoundException):
        authorize_admin_setup(SecretStr(configured))


@pytest.mark.parametrize("key", [None, "", "wrong", "x" * 32, "x" * 257])
async def test_bad_key_cannot_touch_database(enabled, key):
    session = SimpleNamespace(execute=AsyncMock(), add=Mock(), flush=AsyncMock(), commit=AsyncMock())
    with pytest.raises(ForbiddenException):
        await AdminSignupService(session).signup(body(), SecretStr(key) if key is not None else None)
    session.execute.assert_not_awaited()
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


async def test_disabled_cannot_touch_database(enabled, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SIGNUP_ENABLED", False)
    session = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(NotFoundException):
        await AdminSignupService(session).signup(body(), SecretStr(KEY))
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("change", [
    {"email": "not-an-email"}, {"name": "   "}, {"name": "x" * 256},
    {"password": "x" * 15}, {"password": "x" * 129},
    {"role_ids": ["role_ceo"]}, {"mfa_required": False}, {"garage_scope": None},
    {"is_active": False}, {"role": "admin"},
])
def test_invalid_and_privilege_fields_rejected(change):
    with pytest.raises(ValidationError):
        AdminSignupRequest.model_validate({
            "email": "admin@example.com", "name": "Admin", "password": PASSWORD, **change,
        })


def test_password_whitespace_preserved_and_repr_redacted():
    data = AdminSignupRequest(email="admin@example.com", name=" Admin ", password=" " + PASSWORD + " ")
    assert data.name == "Admin"
    assert data.password.get_secret_value() == " " + PASSWORD + " "
    assert PASSWORD not in repr(data)


async def test_existing_accounts_checked_under_table_lock(enabled):
    existing = Mock()
    existing.scalar_one_or_none.return_value = "existing-account-even-if-inactive"
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[Mock(), Mock(), existing]), add=Mock(), commit=AsyncMock(),
    )
    with pytest.raises(ConflictException):
        await AdminSignupService(session).signup(body(), SecretStr(KEY))
    queries = [str(call.args[0]) for call in session.execute.await_args_list]
    assert queries[0] == "SET LOCAL lock_timeout = '5s'"
    assert queries[1] == "LOCK TABLE admin_accounts IN SHARE ROW EXCLUSIVE MODE"
    assert "SELECT admin_accounts.id" in queries[2]
    assert "WHERE" not in queries[2]  # Inactive accounts must also close registration.
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


async def test_lock_failure_is_redacted_and_rolled_back(enabled):
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=OperationalError("private statement", {}, Exception("private error"))),
        rollback=AsyncMock(), add=Mock(),
    )
    with pytest.raises(AppException) as error:
        await AdminSignupService(session).signup(body(), SecretStr(KEY))
    assert error.value.status_code == 503
    assert "private" not in error.value.message
    session.rollback.assert_awaited_once()
    session.add.assert_not_called()
