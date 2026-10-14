"""Customer JWTs cannot be decoded as garage or administrative credentials."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

ISSUER = "gofixcarz-customer-app"
AUDIENCE = "gofixcarz-customer"


def now():
    return datetime.now(timezone.utc)


def otp_digest(challenge_id, identifier, purpose, otp):
    payload = f"{challenge_id}:{identifier}:{purpose}:{otp}"
    return hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def access_token(customer_id, session_id):
    return jwt.encode({
        "sub": str(customer_id), "sid": str(session_id), "role": "customer",
        "type": "customer_access", "iss": ISSUER, "aud": AUDIENCE,
        "iat": now(), "exp": now() + timedelta(minutes=15),
    }, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_customer_access(token):
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            audience=AUDIENCE, issuer=ISSUER,
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
        if payload.get("type") != "customer_access" or payload.get("role") != "customer":
            return None
        if not isinstance(payload.get("sid"), str) or not isinstance(payload.get("sub"), str):
            return None
        return payload
    except JWTError:
        return None
