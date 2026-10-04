"""Disposable loopback-only PostgreSQL; never import application settings."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urlencode

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest


@dataclass(frozen=True)
class TLSCase:
    certificate: str
    mode: str
    root: str = "trusted"
    failure: str | None = None
    crl: bool = False


CASES = [
    TLSCase("valid", "verify-full"),
    TLSCase("valid", "verify-ca"),
    TLSCase("valid", "verify-full", "untrusted", "ca"),
    TLSCase("valid", "verify-ca", "untrusted", "ca"),
    TLSCase("expired", "verify-full", failure="expired"),
    TLSCase("expired", "verify-ca", failure="expired"),
    TLSCase("mismatch", "verify-full", failure="hostname"),
    TLSCase("mismatch", "verify-ca"),
    TLSCase("valid", "require"),
    TLSCase("plaintext", "require", failure="no-tls"),
    TLSCase("plaintext", "disable"),
    # Same CA, key, validity and hostname; only the revoked serial is in the CRL.
    TLSCase("valid", "verify-full", crl=True),
    TLSCase("valid", "verify-ca", crl=True),
    TLSCase("revoked", "verify-full", failure="revoked", crl=True),
    TLSCase("revoked", "verify-ca", failure="revoked", crl=True),
    # Prove that the revoked leaf is otherwise valid without revocation checking.
    TLSCase("revoked", "verify-full"),
    TLSCase("revoked", "verify-ca"),
]


def _case_id(case):
    suffix = "-crl" if case.crl else ""
    return f"{case.certificate}-{case.mode}-{case.root}{suffix}"


def _name(common_name):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _certificate_files(directory):
    """Fresh keys, certificates and a CA-signed CRL revoking only one valid leaf."""
    directory.mkdir(mode=0o700)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = _name("Disposable TLS test CA")
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    (directory / "trusted.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_name = _name("Unrelated TLS test CA")
    other_ca = (
        x509.CertificateBuilder()
        .subject_name(other_name).issuer_name(other_name)
        .public_key(other_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(other_key, hashes.SHA256())
    )
    (directory / "untrusted.pem").write_bytes(
        other_ca.public_bytes(serialization.Encoding.PEM)
    )
    matching_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for kind in ("valid", "revoked", "expired", "mismatch"):
        key = (
            matching_key if kind in {"valid", "revoked"}
            else rsa.generate_private_key(public_exponent=65537, key_size=2048)
        )
        matches = kind != "mismatch"
        san = (
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
            if matches else x509.DNSName("wrong-host.invalid")
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name("127.0.0.1" if matches else "wrong-host.invalid"))
            .issuer_name(ca_name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now - timedelta(days=1) if kind == "expired"
                             else now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([san]), critical=False)
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        (directory / f"{kind}.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path = directory / f"{kind}.key"
        # Create with private permissions, not chmod after exposing a key.
        with os.fdopen(
            os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb",
        ) as out:
            out.write(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
        if kind == "revoked":
            revoked_serial = cert.serial_number
    revoked = (
        x509.RevokedCertificateBuilder()
        .serial_number(revoked_serial)
        .revocation_date(now - timedelta(hours=1))
        .build()
    )
    crl = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(ca_name)
        .last_update(now - timedelta(hours=1))
        .next_update(now + timedelta(days=1))
        .add_revoked_certificate(revoked)
        .sign(ca_key, hashes.SHA256())
    )
    (directory / "revocations.pem").write_bytes(crl.public_bytes(serialization.Encoding.PEM))


@pytest.fixture(scope="module")
def local_cluster():
    """Fail explicitly if prerequisites are absent; no silent skips in release checks."""
    binaries = {name: shutil.which(name) for name in ("initdb", "pg_ctl", "postgres")}
    missing = [name for name, path in binaries.items() if not path]
    if missing:
        pytest.fail(f"Local TLS tests require PostgreSQL binaries: {', '.join(missing)}")
    if os.geteuid() == 0:
        pytest.fail("Run local TLS tests as a non-root user (PostgreSQL requirement)")
    with tempfile.TemporaryDirectory(prefix="garage-local-tls-") as temp:
        base = Path(temp)
        home = base / "home"
        home.mkdir(mode=0o700)
        # Clean environment for libpq/asyncpg AND subprocesses. No .env, service
        # files, default client certs, passfiles, or injected connection settings.
        with pytest.MonkeyPatch.context() as patch:
            for name in list(os.environ):
                if name.startswith("PG") or name in {
                    "DATABASE_URL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                }:
                    patch.delenv(name)
            patch.setenv("HOME", str(home))
            certs = base / "test certs"
            _certificate_files(certs)
            data = base / "data"
            env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "LC_ALL": "C"}
            subprocess.run(
                [binaries["initdb"], "-D", str(data), "-U", "tls_test",
                 "-A", "trust", "--no-locale", "--encoding=UTF8"],
                env=env, check=True, capture_output=True, text=True, timeout=30,
            )
            # No external interface and no Unix socket authentication paths.
            (data / "pg_hba.conf").write_text(
                "host all tls_test 127.0.0.1/32 trust\n", encoding="utf-8",
            )
            yield base, data, certs, binaries["pg_ctl"], env


@pytest.fixture(scope="module", params=CASES, ids=_case_id)
def postgres_tls_case(request, local_cluster):
    base, data, certs, pg_ctl, env = local_cluster
    case = request.param
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    tls = case.certificate != "plaintext"
    config = [
        "listen_addresses = '127.0.0.1'",
        f"port = {port}",
        "unix_socket_directories = ''",
        "max_connections = 10",
        "shared_buffers = '12MB'",
        f"ssl = {'on' if tls else 'off'}",
    ]
    if tls:
        config += [
            f"ssl_cert_file = '{certs / (case.certificate + '.pem')}'",
            f"ssl_key_file = '{certs / (case.certificate + '.key')}'",
        ]
    (data / "postgresql.conf").write_text("\n".join(config) + "\n", encoding="utf-8")
    log = base / "postgres.log"
    try:
        started = subprocess.run(
            [pg_ctl, "-D", str(data), "-l", str(log), "-w", "-t", "10", "start"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        if started.returncode:
            pytest.fail(f"Disposable PostgreSQL failed to start:\n{log.read_text()}")
        query = {"sslmode": case.mode, "sslrootcert": str(certs / f"{case.root}.pem")}
        if case.crl:
            query["sslcrl"] = str(certs / "revocations.pem")
        # All destination/auth fields are hardcoded test values, never settings.
        url = f"postgresql://tls_test:disposable@127.0.0.1:{port}/postgres?{urlencode(query)}"
        yield case, url
    finally:
        if (data / "postmaster.pid").exists():
            subprocess.run(
                [pg_ctl, "-D", str(data), "-m", "immediate", "-w", "-t", "10", "stop"],
                env=env, check=True, capture_output=True, text=True, timeout=20,
            )