from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _build_async_url(db_url: str) -> tuple[str, dict]:
    """
    Convert a standard postgres:// URL to postgresql+asyncpg://
    and extract sslmode into connect_args (asyncpg doesn't accept sslmode in the URL).
    """
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(db_url)
    params = parse_qs(parsed.query)

    # Strip sslmode — Replit's internal Postgres doesn't use SSL.
    # For external Postgres that requires SSL, pass ssl=True in connect_args.
    ssl_mode = params.pop("sslmode", [None])[0]
    connect_args: dict = {}
    # Only force SSL for remote/production databases (not Replit-internal helium host)
    parsed_host = params  # reuse parsed below
    host = urlparse(db_url).hostname or ""
    if ssl_mode in ("require", "verify-ca", "verify-full") and host not in ("localhost", "helium", "127.0.0.1"):
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        connect_args["ssl"] = ctx

    new_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(query=new_query))
    return clean_url, connect_args


_db_url, _connect_args = _build_async_url(settings.DATABASE_URL)

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args=_connect_args,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
