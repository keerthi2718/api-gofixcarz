"""Alembic env.py — uses synchronous psycopg2 for reliable migration execution."""
import os
import sys
from logging.config import fileConfig
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from alembic import context
from sqlalchemy import create_engine, pool

# Make sure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402

# Import all models so they register on Base.metadata
from app.models import (  # noqa: F401, E402
    User, Garage, Customer, Vehicle, Booking, Job, JobTimeline, ServicePackage, Notification
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _build_sync_url(db_url: str) -> str:
    """Convert the DATABASE_URL to a psycopg2-compatible sync URL."""
    # Strip asyncpg scheme if present
    if "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "")
    # postgres:// → postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    # Strip sslmode from URL query (psycopg2 accepts it via connect_args instead)
    parsed = urlparse(db_url)
    params = parse_qs(parsed.query)
    params.pop("sslmode", None)
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


_sync_url = _build_sync_url(settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        _sync_url,
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
