"""Shared synchronous migration URL conversion (never log the URL)."""
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from app.database.connection_url import is_internal_helium


def build_sync_url(db_url: str) -> str:
    if "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(db_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    # psycopg2 understands libpq SSL options directly. Never strip the remote
    # policy: both Alembic and production preflight must honor verification.
    if is_internal_helium(parsed, params):
        params["sslmode"] = ["disable"]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))