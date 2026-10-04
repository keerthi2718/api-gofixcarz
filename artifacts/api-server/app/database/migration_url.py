"""Shared synchronous migration URL conversion (never log the URL)."""
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def build_sync_url(db_url: str) -> str:
    if "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(db_url)
    params = parse_qs(parsed.query)
    # Preserve the existing Alembic conversion policy.
    params.pop("sslmode", None)
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))