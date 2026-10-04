"""Real handshakes through the URL helpers and SQLAlchemy driver adapters."""
import ssl

import asyncpg
import psycopg2
import pytest
from sqlalchemy import create_engine, pool, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.connection_url import build_async_url
from app.database.migration_url import build_sync_url


pytestmark = pytest.mark.local_tls
PROBE = text(
    "SELECT current_user, ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
)


def _assert_sync_failure(error, failure):
    assert isinstance(error.orig, psycopg2.OperationalError)
    message = str(error.orig).lower()
    if failure in {"ca", "expired"}:
        assert "certificate verify failed" in message
    elif failure == "hostname":
        assert "does not match host name" in message
    else:
        assert "server does not support ssl, but ssl was required" in message


def test_psycopg2_tls_policy(postgres_tls_case):
    case, url = postgres_tls_case
    engine = create_engine(
        build_sync_url(url), poolclass=pool.NullPool,
        connect_args={"connect_timeout": 3},
    )
    assert engine.dialect.driver == "psycopg2"
    try:
        if case.failure:
            with pytest.raises(OperationalError) as caught:
                with engine.connect():
                    pytest.fail("Unsafe connection unexpectedly succeeded")
            _assert_sync_failure(caught.value, case.failure)
        else:
            with engine.connect() as connection:
                user, encrypted = connection.execute(PROBE).one()
                assert user == "tls_test"
                assert encrypted is (case.certificate != "plaintext")
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_asyncpg_tls_policy(postgres_tls_case):
    case, url = postgres_tls_case
    async_url, args = build_async_url(url)
    engine = create_async_engine(
        async_url, connect_args={**args, "timeout": 3}, poolclass=pool.NullPool,
    )
    assert engine.dialect.driver == "asyncpg"
    try:
        if case.failure == "no-tls":
            with pytest.raises(
                (ConnectionError, asyncpg.exceptions.ConnectionDoesNotExistError),
                match="rejected SSL",
            ):
                async with engine.connect():
                    pytest.fail("Non-TLS server unexpectedly accepted require")
        elif case.failure:
            with pytest.raises(ssl.SSLCertVerificationError) as caught:
                async with engine.connect():
                    pytest.fail("Unsafe connection unexpectedly succeeded")
            message = caught.value.verify_message.lower()
            if case.failure == "expired":
                assert "expired" in message
            elif case.failure == "hostname":
                assert "mismatch" in message
            else:
                assert "issuer" in message or "self-signed" in message
        else:
            async with engine.connect() as connection:
                user, encrypted = (await connection.execute(PROBE)).one()
                assert user == "tls_test"
                assert encrypted is (case.certificate != "plaintext")
    finally:
        await engine.dispose()