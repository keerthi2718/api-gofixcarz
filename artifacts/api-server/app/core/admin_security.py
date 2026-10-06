"""Separate token purpose/audience and salted scrypt password hashing."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

ACCESS_SECONDS = 900
AUDIENCE = "gofixcarz-admin"
ISSUER = "gofixcarz-api"


def hash_admin_password(password: str) -> str:
    if not 16 <= len(password) <= 128:
        raise ValueError("Admin password must contain 16 to 128 characters.")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_admin_password(password: str, stored: str) -> bool:
    try:
        kind, salt, expected = stored.split("$")
        if kind != "scrypt" or len(password) > 128:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def admin_access_token(account, session) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(account.id), "sid": str(session.id), "role": "admin",
        "type": "admin_access", "aud": AUDIENCE, "iss": ISSUER,
        "ver": account.credential_version, "iat": now,
        "exp": now + timedelta(seconds=ACCESS_SECONDS), "jti": secrets.token_urlsafe(16),
    }, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_admin_access(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            audience=AUDIENCE, issuer=ISSUER,
            options={"require_exp": True, "require_iat": True, "require_sub": True,
                     "require_aud": True, "require_iss": True},
        )
        if payload.get("type") != "admin_access" or payload.get("role") != "admin":
            return None
        if not isinstance(payload.get("sid"), str) or not isinstance(payload.get("ver"), int):
            return None
        return payload
    except (JWTError, ValueError, TypeError):
        return None
