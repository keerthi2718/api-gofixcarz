"""Production preflight: require delivery schema; upgrades need explicit opt-in."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool, text

from app.database.migration_url import build_sync_url


BASELINE = "0007_garage_logo_url"
DELIVERY_TABLE = "0008_sms_delivery"
DELIVERY_HEAD = "0009_sms_delivery_retention"
# Transaction-level lock serializes concurrently starting production instances.
MIGRATION_LOCK = 70991009


def ensure_delivery_schema(database_url: str, *, allow_upgrade: bool = False) -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    # Deliberately bounded: don't silently authorize future/unrelated migrations.
    if ScriptDirectory.from_config(config).get_heads() != [DELIVERY_HEAD]:
        raise RuntimeError("Migration head changed; review the production preflight")
    engine = create_engine(build_sync_url(database_url), poolclass=pool.NullPool)
    try:
        with engine.begin() as connection:
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