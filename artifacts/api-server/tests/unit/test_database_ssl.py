"""Dummy URLs only: no settings imports, secret lookups, or connections."""
import inspect
import ssl
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

import pytest
from asyncpg import connect_utils
from sqlalchemy import create_engine, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.connection_url import SSL_MODES, build_async_url
from app.database.migration_url import build_sync_url


PREFIXES = ["postgres://", "postgresql://", "postgresql+asyncpg://"]
HOSTS = ["db.example.invalid", "localhost", "127.0.0.1", "[::1]", "helium.example.invalid"]


@pytest.mark.parametrize("prefix", PREFIXES)
@pytest.mark.parametrize("mode", sorted(SSL_MODES))
@pytest.mark.parametrize("host", HOSTS)
def test_requested_remote_and_local_policy_is_preserved(prefix, mode, host):
    original = f"{prefix}dummy:p%40ss@{host}:5432/dummy?sslmode={mode}"
    sync_url = build_sync_url(original)
    async_url, args = build_async_url(original)
    assert sync_url.startswith("postgresql://")
    assert async_url.startswith("postgresql+asyncpg://")
    assert urlparse(sync_url).netloc == urlparse(original).netloc
    assert urlparse(async_url).netloc == urlparse(original).netloc
    assert parse_qs(urlparse(sync_url).query) == {"sslmode": [mode]}
    assert urlparse(async_url).query == ""
    assert args == {"ssl": mode}
    # Exercise SQLAlchemy's driver argument conversion without connecting.
    sync_engine = create_engine(sync_url, poolclass=pool.NullPool)
    _, sync_kwargs = sync_engine.dialect.create_connect_args(sync_engine.url)
    assert sync_kwargs["sslmode"] == mode
    sync_engine.dispose()


@pytest.mark.parametrize("mode", [None, *sorted(SSL_MODES)])
@pytest.mark.parametrize("host", ["helium", "HELIUM"])
def test_only_internal_helium_explicitly_disables_ssl(mode, host):
    query = f"?sslmode={mode}" if mode else ""
    original = f"postgresql://dummy:dummy@{host}/dummy{query}"
    assert parse_qs(urlparse(build_sync_url(original)).query)["sslmode"] == ["disable"]
    assert build_async_url(original)[1] == {"ssl": False}


@pytest.mark.parametrize("authority,override,internal", [
    ("helium", "db.example.invalid", False),
    ("db.example.invalid", "helium", True),
    ("helium", "helium,db.example.invalid", False),
])
def test_host_override_cannot_accidentally_exempt_remote_host(authority, override, internal):
    original = (
        f"postgresql://dummy:dummy@{authority}/dummy"
        f"?host={override}&sslmode=verify-full"
    )
    sync_query = parse_qs(urlparse(build_sync_url(original)).query)
    assert sync_query["sslmode"] == ["disable" if internal else "verify-full"]
    assert build_async_url(original)[1] == {"ssl": False if internal else "verify-full"}


@pytest.mark.parametrize("host,query,expected_host,expected_mode", [
    ("helium", "host=db.example.invalid&host=helium", "db.example.invalid,helium", "verify-full"),
    ("helium", "host=helium&host=db.example.invalid", "helium,db.example.invalid", "verify-full"),
    ("helium", "host=db.example.invalid,helium", "db.example.invalid,helium", "verify-full"),
    ("helium", "host=helium&host=helium", "helium,helium", "disable"),
    ("helium", "hostaddr=203.0.113.7", "helium", "verify-full"),
    ("db.example.invalid", "host=helium&hostaddr=203.0.113.7", "helium", "verify-full"),
    ("helium", "hostaddr=203.0.113.7,203.0.113.8", "helium", "verify-full"),
    ("helium", "hostaddr=", "helium", "verify-full"),
    ("helium", "service=dummy", "helium", "verify-full"),
])
def test_sync_driver_destinations_never_downgrade_remote_ssl(host, query, expected_host, expected_mode):
    original = (
        f"postgresql://dummy:dummy@{host}/dummy?"
        f"{query}&sslmode=verify-full&sslrootcert=%2Fdummy-ca.pem"
    )
    engine = create_engine(build_sync_url(original), poolclass=pool.NullPool)
    _, kwargs = engine.dialect.create_connect_args(engine.url)
    assert kwargs["host"] == expected_host
    assert kwargs["sslmode"] == expected_mode
    assert kwargs["sslrootcert"] == "/dummy-ca.pem"
    for option in ("hostaddr", "service"):
        if option in parse_qs(query, keep_blank_values=True):
            # SQLAlchemy omits blank query values before driver invocation.
            assert kwargs.get(option, "") == parse_qs(query, keep_blank_values=True)[option][-1]
    engine.dispose()
    assert build_async_url(original)[1]["ssl"] == (
        False if expected_mode == "disable" else "verify-full"
    )


@pytest.mark.parametrize("host", HOSTS)
def test_absent_policy_preserves_driver_default(host):
    original = f"postgresql://dummy:dummy@{host}/dummy"
    assert build_sync_url(original) == original
    assert build_async_url(original)[1] == {}


def test_certificate_and_unrelated_url_options_are_preserved():
    original = (
        "postgresql://dummy:p%2Bss@db.example.invalid/dummy?"
        "sslmode=verify-full&sslrootcert=%2Fdummy%20ca.pem&"
        "sslcert=%2Fdummy-client.pem&sslkey=%2Fdummy-key.pem&"
        "sslcrl=%2Fdummy-crl.pem&ssl_min_protocol_version=TLSv1.2&"
        "command_timeout=5&unused=&repeat=one&repeat=two"
    )
    sync_query = parse_qs(urlparse(build_sync_url(original)).query, keep_blank_values=True)
    assert sync_query == parse_qs(urlparse(original).query, keep_blank_values=True)
    async_url, args = build_async_url(original)
    assert args["ssl"] == "verify-full"
    ssl_query = parse_qs(urlparse(args["dsn"]).query)
    assert ssl_query == {k: v for k, v in sync_query.items() if k.startswith("ssl") and k != "sslmode"}
    assert not urlparse(args["dsn"]).netloc  # No duplicate credentials in SSL DSN.
    assert parse_qs(urlparse(async_url).query, keep_blank_values=True) == {
        "command_timeout": ["5"], "unused": [""], "repeat": ["one", "two"],
    }


@pytest.mark.parametrize("mode", ["", "invalid", "VERIFY-FULL"])
def test_invalid_async_mode_fails_without_leaking_url(mode):
    with pytest.raises(ValueError, match="^Invalid PostgreSQL sslmode$"):
        build_async_url(f"postgresql://dummy:private@db.example.invalid/dummy?sslmode={mode}")


def test_unsupported_async_ssl_option_fails_explicitly():
    with pytest.raises(ValueError, match="^Unsupported PostgreSQL SSL option$"):
        build_async_url("postgresql://dummy:dummy@db.example.invalid/dummy?sslunknown=value")


@pytest.fixture
def native_parser(monkeypatch):
    # Prevent asyncpg's pure parser from consulting environment credentials or
    # ~/.postgresql files. This parser performs no DNS or socket operations.
    monkeypatch.setattr(connect_utils.os, "environ", {})
    monkeypatch.setattr(connect_utils.os, "getenv", lambda key, default=None: default)
    monkeypatch.setattr(connect_utils.compat, "get_pg_home_directory", lambda: None)
    # Newer asyncpg versions have a separate helper for TLS file defaults.
    if hasattr(connect_utils, "_dot_postgresql_path"):
        monkeypatch.setattr(connect_utils, "_dot_postgresql_path", lambda name: None)
    load_ca = Mock()
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", load_ca)

    def parse(args):
        parser = connect_utils._parse_connect_dsn_and_args
        kwargs = {name: None for name in inspect.signature(parser).parameters}
        kwargs.update(
            host="db.example.invalid", port=5432, user="dummy", password="dummy",
            database="dummy", direct_tls=False,
        )
        kwargs.update(args)
        return parser(**kwargs)[1]

    return parse, load_ca


@pytest.mark.parametrize("mode,verify,hostname", [
    ("verify-ca", ssl.CERT_REQUIRED, False),
    ("verify-full", ssl.CERT_REQUIRED, True),
    ("require", ssl.CERT_NONE, False),
    ("allow", ssl.CERT_NONE, False),
    ("prefer", ssl.CERT_NONE, False),
])
def test_native_asyncpg_enforces_requested_verification(native_parser, mode, verify, hostname):
    parse, load_ca = native_parser
    query = f"sslmode={mode}"
    if mode.startswith("verify"):
        query += "&sslrootcert=%2Fdummy-ca.pem"
    async_url, args = build_async_url(
        f"postgresql://dummy:dummy@db.example.invalid/dummy?{query}",
    )
    engine = create_async_engine(async_url, connect_args=args, poolclass=pool.NullPool)
    _, driver_kwargs = engine.dialect.create_connect_args(engine.url)
    params = parse({**driver_kwargs, **args})
    assert params.ssl.verify_mode == verify
    assert params.ssl.check_hostname is hostname
    if mode.startswith("verify"):
        load_ca.assert_called_once_with(cafile="/dummy-ca.pem")


def test_unusable_ca_fails_instead_of_downgrading(native_parser):
    parse, load_ca = native_parser
    load_ca.side_effect = ssl.SSLError("dummy invalid CA")
    _, args = build_async_url(
        "postgresql://dummy:dummy@db.example.invalid/dummy?"
        "sslmode=verify-full&sslrootcert=%2Fdummy-ca.pem",
    )
    with pytest.raises(ssl.SSLError, match="dummy invalid CA"):
        parse(args)


@pytest.mark.parametrize("host,mode", [
    ("db.example.invalid", "disable"), ("helium", "verify-full"),
])
def test_native_asyncpg_disables_tls_only_when_requested_or_internal(native_parser, host, mode):
    parse, load_ca = native_parser
    _, args = build_async_url(
        f"postgresql://dummy:dummy@{host}/dummy?"
        f"sslmode={mode}&sslrootcert=%2Fdummy-ca.pem",
    )
    assert not parse(args).ssl
    load_ca.assert_not_called()