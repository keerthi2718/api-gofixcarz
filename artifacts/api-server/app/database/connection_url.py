"""Pure URL helpers: no settings, credentials, engines, or network access."""
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


SSL_MODES = frozenset({
    "disable", "allow", "prefer", "require", "verify-ca", "verify-full",
})
# These libpq DSN options are also understood by asyncpg, but SQLAlchemy
# cannot forward them as asyncpg.connect keyword arguments.
SSL_DSN_OPTIONS = frozenset({
    "sslcert", "sslkey", "sslrootcert", "sslcrl", "sslpassword",
    "ssl_min_protocol_version", "ssl_max_protocol_version",
})


def is_internal_helium(parsed, params: dict) -> bool:
    """Exempt only exclusively helium destinations, never ambiguous overrides."""
    # libpq can connect to hostaddr while using host only for authentication.
    # A service file may also supply addresses we cannot establish as internal.
    if "hostaddr" in params or "service" in params:
        return False
    # SQLAlchemy combines repeated query hosts into a libpq multi-host list.
    # Checking only the last value would disable TLS for earlier remote hosts.
    hosts = params.get("host", [parsed.hostname or ""])
    return all(
        host.lower() == "helium"
        for value in hosts
        for host in value.split(",")
    )


def build_async_url(db_url: str) -> tuple[str, dict]:
    """Translate libpq SSL options without weakening asyncpg's native policy.

    asyncpg accepts all six libpq modes through its ``ssl`` argument, including
    CA validation for verify-ca and CA + hostname validation for verify-full.
    Companion certificate options go through a credential-free SSL-only DSN.
    """
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(db_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    internal = is_internal_helium(parsed, params)
    ssl_mode = params.pop("sslmode", [None])[-1]
    ssl_options = {}
    for key in list(params):
        if key.startswith("ssl"):
            if key not in SSL_DSN_OPTIONS:
                raise ValueError("Unsupported PostgreSQL SSL option")
            ssl_options[key] = params.pop(key)

    connect_args: dict = {}
    if internal:
        # Helium does not support TLS, even when the injected URL requests it.
        connect_args["ssl"] = False
    else:
        if ssl_mode is not None:
            if ssl_mode not in SSL_MODES:
                raise ValueError("Invalid PostgreSQL sslmode")
            connect_args["ssl"] = ssl_mode
        if ssl_options:
            connect_args["dsn"] = "postgresql://?" + urlencode(ssl_options, doseq=True)

    clean_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
    return clean_url, connect_args