"""Production preflight: require delivery schema; upgrades need explicit opt-in."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, String, create_engine, inspect, pool, text

from app.database.migration_url import build_sync_url


BASELINE = "0007_garage_logo_url"
DELIVERY_TABLE = "0008_sms_delivery"
DELIVERY_HEAD = "0009_sms_delivery_retention"
# The admin-role migration follows the approved delivery target. Recognizing
# this known head does not authorize applying it during delivery-only startup.
REVIEWED_CODE_HEAD = "0014_admin_challenge_binding"
# Transaction-level lock serializes concurrently starting production instances.
MIGRATION_LOCK = 70991009


def check_delivery_schema(connection) -> None:
    """Inspect actual schema without DDL or changing Alembic's revision record.

    Managed publishing syncs schema, not the contents of alembic_version.
    A stale revision alone must not block a structurally ready database.
    """
    inspector = inspect(connection)
    if not inspector.has_table("sms_deliveries"):
        raise RuntimeError("Delivery schema is missing; review publishing schema changes")
    columns = {column["name"]: column for column in inspector.get_columns("sms_deliveries")}
    for name, length, nullable in (
        ("request_id", 128, False), ("status", 16, False),
        ("failure_category", 32, True),
    ):
        column = columns.get(name)
        if (
            column is None or not isinstance(column["type"], String)
            or column["type"].length != length or column["nullable"] != nullable
        ):
            raise RuntimeError("Delivery schema is incompatible; review publishing schema changes")
    for name, nullable in (
        ("accepted_at", True), ("reported_at", True), ("created_at", False),
    ):
        column = columns.get(name)
        if (
            column is None or not isinstance(column["type"], DateTime)
            or not column["type"].timezone or column["nullable"] != nullable
        ):
            raise RuntimeError("Delivery schema is incompatible; review publishing schema changes")
    if inspector.get_pk_constraint("sms_deliveries").get("constrained_columns") != ["request_id"]:
        raise RuntimeError("Delivery schema primary key is incompatible")
    indexes = inspector.get_indexes("sms_deliveries")
    if not any(index["name"] == "ix_sms_deliveries_retention_started_at" for index in indexes):
        raise RuntimeError("Delivery retention index is missing; review publishing schema changes")


def ensure_delivery_schema(database_url: str, *, allow_upgrade: bool = False) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    # Deliberately bounded: don't silently authorize future/unrelated migrations.
    if allow_upgrade and ScriptDirectory.from_config(config).get_heads() not in (
        [DELIVERY_HEAD], [REVIEWED_CODE_HEAD],
    ):
        raise RuntimeError("Migration head changed; review the production preflight")
    engine = create_engine(build_sync_url(database_url), poolclass=pool.NullPool)
    try:
        with engine.begin() as connection:
            if not allow_upgrade:
                check_delivery_schema(connection)
                return
            if allow_upgrade:
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {
                    "key": MIGRATION_LOCK,
                })
            current = MigrationContext.configure(connection).get_current_heads()
            if current == (DELIVERY_HEAD,):
                return
            if current not in ((BASELINE,), (DELIVERY_TABLE,)):
                raise RuntimeError(
                    "Database baseline is unsupported; review older migrations separately"
                )
            if not allow_upgrade:
                raise RuntimeError(
                    "Delivery migrations are missing; obtain approval before setting "
                    "APPLY_DELIVERY_MIGRATIONS=1 for production startup"
                )
            config.attributes["connection"] = connection
            command.upgrade(config, DELIVERY_HEAD)
            if MigrationContext.configure(connection).get_current_heads() != (DELIVERY_HEAD,):
                raise RuntimeError("Delivery migration verification failed")
    finally:
        engine.dispose()