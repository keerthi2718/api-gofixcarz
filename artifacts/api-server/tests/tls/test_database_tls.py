"""Real handshakes through the URL helpers and SQLAlchemy driver adapters."""
import ssl
from datetime import datetime, timezone

import asyncpg
from cryptography import x509
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
    if failure == "crl-signature":
        # libpq may surface the first RSA error from OpenSSL's error queue
        # instead of the final certificate verification error. Fresh unrelated
        # keys can fail at either the modulus or PKCS#1 padding check.
        assert "ssl error:" in message
        assert any(reason in message for reason in (
            "certificate verify failed", "crl signature failure",
            "invalid padding", "padding check failed", "data too large for modulus",
        ))
    elif failure in {"ca", "expired", "revoked", "crl-expired"}:
        # libpq exposes the generic OpenSSL failure, not the verification code.
        # The same leaf succeeds without a CRL in the control cases.
        assert "certificate verify failed" in message
    elif failure == "hostname":
        assert "does not match host name" in message
    else:
        assert "server does not support ssl, but ssl was required" in message


def test_crl_material_isolated_failures(local_cluster):
    """Check the fixtures cannot pass by accidentally testing a different defect."""
    _, _, certs, _, _ = local_cluster
    ca = x509.load_pem_x509_certificate((certs / "trusted.pem").read_bytes())
    valid_leaf = x509.load_pem_x509_certificate((certs / "valid.pem").read_bytes())
    revoked_leaf = x509.load_pem_x509_certificate((certs / "revoked.pem").read_bytes())
    now = datetime.now(timezone.utc)
    for kind in ("valid", "expired", "bad-signature"):
        crl = x509.load_pem_x509_crl(
            (certs / f"revocations-{kind}.pem").read_bytes()
        )
        assert crl.issuer == ca.subject
        assert crl.last_update_utc < now
        assert (crl.next_update_utc < now) is (kind == "expired")
        assert crl.is_signature_valid(ca.public_key()) is (kind != "bad-signature")
        assert crl.get_revoked_certificate_by_serial_number(valid_leaf.serial_number) is None
        assert crl.get_revoked_certificate_by_serial_number(revoked_leaf.serial_number) is not None


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
            elif case.failure == "revoked":
                assert caught.value.verify_code == 23  # X509_V_ERR_CERT_REVOKED
                assert "revoked" in message
            elif case.failure == "crl-expired":
                assert caught.value.verify_code == 12  # X509_V_ERR_CRL_HAS_EXPIRED
                assert "crl has expired" in message
            elif case.failure == "crl-signature":
                assert caught.value.verify_code == 8  # X509_V_ERR_CRL_SIGNATURE_FAILURE
                assert "crl signature failure" in message
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