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
    inspector = Mock()
    inspector.has_table.return_value = True
    inspector.get_columns.return_value = [
        {"name": name, "type": migrations.String(length), "nullable": nullable}
        for name, length, nullable in (
            ("request_id", 128, False), ("status", 16, False),
            ("failure_category", 32, True),
        )
    ] + [
        {"name": name, "type": migrations.DateTime(timezone=True), "nullable": nullable}
        for name, nullable in (
            ("accepted_at", True), ("reported_at", True), ("created_at", False),
        )
    ]
    inspector.get_pk_constraint.return_value = {"constrained_columns": ["request_id"]}
    inspector.get_indexes.return_value = [{"name": "ix_sms_deliveries_retention_started_at"}]
    monkeypatch.setattr(migrations, "inspect", Mock(return_value=inspector))
    return engine, connection, context, upgrade


def test_current_schema_is_read_only(gateway):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = (migrations.DELIVERY_HEAD,)
    migrations.ensure_delivery_schema("postgresql://test@localhost/test")
    connection.execute.assert_not_called()
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_production_preflight_preserves_ssl_policy(gateway, mode):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = (migrations.DELIVERY_HEAD,)
    url = (
        f"postgresql+asyncpg://dummy:dummy@db.example.invalid/dummy?"
        f"sslmode={mode}&sslrootcert=%2Fdummy-ca.pem"
    )
    migrations.ensure_delivery_schema(url)
    migrations.create_engine.assert_called_once_with(
        url.replace("postgresql+asyncpg://", "postgresql://"),
        poolclass=migrations.pool.NullPool,
    )
    connection.execute.assert_not_called()
    upgrade.assert_not_called()


@pytest.mark.parametrize("baseline", [migrations.BASELINE, migrations.DELIVERY_TABLE])
def test_pending_migrations_require_approval(gateway, baseline):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = (baseline,)
    migrations.inspect.return_value.has_table.return_value = False
    with pytest.raises(RuntimeError, match="review publishing schema changes"):
        migrations.ensure_delivery_schema("postgresql://test@localhost/test")
    connection.execute.assert_not_called()
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("heads", [
    (), ("0002_add_refresh_tokens",), (migrations.BASELINE,), (migrations.DELIVERY_HEAD,),
])
def test_publish_synced_schema_does_not_require_alembic_revision(gateway, heads):
    engine, connection, context, upgrade = gateway
    context.get_current_heads.return_value = heads
    migrations.ensure_delivery_schema("postgresql://test@localhost/test")
    context.get_current_heads.assert_not_called()
    connection.execute.assert_not_called()
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("damage", ["column", "type", "timezone", "nullable", "pk", "index"])
def test_read_only_guard_rejects_incompatible_schema(gateway, damage):
    _, connection, _, upgrade = gateway
    inspector = migrations.inspect.return_value
    columns = inspector.get_columns.return_value
    if damage == "column":
        columns.pop()
    elif damage == "type":
        columns[0]["type"] = migrations.String(8)
    elif damage == "timezone":
        columns[-1]["type"] = migrations.DateTime(timezone=False)
    elif damage == "nullable":
        columns[0]["nullable"] = True
    elif damage == "pk":
        inspector.get_pk_constraint.return_value = {"constrained_columns": []}
    elif damage == "index":
        inspector.get_indexes.return_value = []
    with pytest.raises(RuntimeError):
        migrations.ensure_delivery_schema("postgresql://test@localhost/test")
    connection.execute.assert_not_called()
    upgrade.assert_not_called()


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


def test_known_admin_head_does_not_expand_delivery_upgrade(gateway):
    _, connection, context, upgrade = gateway
    assert migrations.ScriptDirectory.from_config(
        migrations.Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    ).get_heads() == [migrations.REVIEWED_CODE_HEAD]
    context.get_current_heads.side_effect = [
        (migrations.BASELINE,), (migrations.DELIVERY_HEAD,),
    ]
    migrations.ensure_delivery_schema("postgresql://test@localhost/test", allow_upgrade=True)
    assert upgrade.call_args.args[1] == migrations.DELIVERY_HEAD


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