"""Publishing guard tests: mocked connections only, never production migrations."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.database import delivery_migrations as migrations


@pytest.fixture
def gateway(monkeypatch):
    connection = Mock()
    transaction = Mock()
    transaction.__enter__ = Mock(return_value=connection)
    transaction.__exit__ = Mock(return_value=False)
    engine = Mock()
    engine.begin.return_value = transaction
    factory = Mock(return_value=engine)
    monkeypatch.setattr(migrations, "create_engine", factory)
    context = Mock()
    monkeypatch.setattr(migrations.MigrationContext, "configure", Mock(return_value=context))
    upgrade = Mock()
    monkeypatch.setattr(migrations.command, "upgrade", upgrade)
    return engine, connection, context, upgrade


def test_current_schema_is_read_only(gateway):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = (migrations.DELIVERY_HEAD,)
    migrations.ensure_delivery_schema("postgresql://test@localhost/test")
    connection.execute.assert_not_called()
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("baseline", [migrations.BASELINE, migrations.DELIVERY_TABLE])
def test_pending_migrations_require_approval(gateway, baseline):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = (baseline,)
    with pytest.raises(RuntimeError, match="obtain approval"):
        migrations.ensure_delivery_schema("postgresql://test@localhost/test")
    connection.execute.assert_not_called()
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("baseline", [migrations.BASELINE, migrations.DELIVERY_TABLE])
def test_approved_delivery_upgrade_is_locked_and_bounded(gateway, baseline):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.side_effect = [(baseline,), (migrations.DELIVERY_HEAD,)]
    migrations.ensure_delivery_schema("postgresql://test@localhost/test", allow_upgrade=True)
    statement, params = connection.execute.call_args.args
    assert "pg_advisory_xact_lock" in str(statement)
    assert params == {"key": migrations.MIGRATION_LOCK}
    config, target = upgrade.call_args.args
    assert target == migrations.DELIVERY_HEAD
    assert config.attributes["connection"] is connection
    engine.begin.return_value.__exit__.assert_called_once_with(None, None, None)
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("heads", [
    (), ("0006_jobs_job_number_per_garage",), ("unknown",),
    (migrations.BASELINE, migrations.DELIVERY_HEAD),
])
def test_unrelated_baselines_are_never_upgraded(gateway, heads):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = heads
    with pytest.raises(RuntimeError, match="unsupported"):
        migrations.ensure_delivery_schema("postgresql://test@localhost/test", allow_upgrade=True)
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("failure", ["upgrade", "verification"])
def test_failed_migration_rolls_back(gateway, failure):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = (migrations.BASELINE,)
    if failure == "upgrade":
        upgrade.side_effect = RuntimeError("simulated failure")
    with pytest.raises(RuntimeError):
        migrations.ensure_delivery_schema("postgresql://test@localhost/test", allow_upgrade=True)
    assert engine.begin.return_value.__exit__.call_args.args[0] is RuntimeError
    engine.dispose.assert_called_once()


def test_future_code_head_requires_separate_review(gateway, monkeypatch):
    engine, connection, context, upgrade = gateway
    monkeypatch.setattr(migrations.ScriptDirectory, "from_config", Mock(
        return_value=Mock(get_heads=Mock(return_value=["future_migration"])),
    ))
    with pytest.raises(RuntimeError, match="head changed"):
        migrations.ensure_delivery_schema("postgresql://test@localhost/test", allow_upgrade=True)
    engine.begin.assert_not_called()
    upgrade.assert_not_called()


def load_startup():
    script = Path(__file__).resolve().parents[2] / "scripts" / "production_start.py"
    spec = importlib.util.spec_from_file_location("production_start", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("approval,expected", [(None, False), ("0", False), ("1", True)])
def test_startup_checks_before_exec(monkeypatch, approval, expected):
    startup = load_startup()
    if approval is None:
        monkeypatch.delenv("APPLY_DELIVERY_MIGRATIONS", raising=False)
    else:
        monkeypatch.setenv("APPLY_DELIVERY_MIGRATIONS", approval)
    check = Mock()
    monkeypatch.setattr(migrations, "ensure_delivery_schema", check)
    execvp = Mock()
    monkeypatch.setattr(startup.os, "execvp", execvp)
    monkeypatch.setenv("PORT", "8080")
    assert startup.main() == 0
    assert check.call_args.kwargs == {"allow_upgrade": expected}
    execvp.assert_called_once_with("uvicorn", [
        "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080",
    ])


@pytest.mark.parametrize("approval", ["0", "yes"])
def test_startup_failure_never_serves_or_leaks_details(monkeypatch, capsys, approval):
    startup = load_startup()
    monkeypatch.setenv("APPLY_DELIVERY_MIGRATIONS", approval)
    monkeypatch.setattr(migrations, "ensure_delivery_schema", Mock(
        side_effect=RuntimeError("postgresql://secret:password@private/db"),
    ))
    execvp = Mock()
    monkeypatch.setattr(startup.os, "execvp", execvp)
    assert startup.main() == 1
    execvp.assert_not_called()
    output = capsys.readouterr().err
    assert "API was not started" in output
    assert "password" not in output
    assert "postgresql://" not in output