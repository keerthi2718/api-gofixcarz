"""RFC 6238 TOTP and authenticated encryption; no plaintext factor in storage."""
import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet
from app.core.config import settings


def cipher():
    key = hashlib.sha256(("admin-totp-v1:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def encrypt_secret(secret):
    return cipher().encrypt(secret.encode()).decode()


def decrypt_secret(value):
    return cipher().decrypt(value.encode()).decode()


def totp(secret, counter=None):
    if counter is None:
        counter = int(time.time() // 30)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000
    return f"{value:06d}"


def verify_totp(secret, code, last_counter=None):
    counter = int(time.time() // 30)
    for candidate in (counter - 1, counter, counter + 1):
        if (last_counter is None or candidate > last_counter) and hmac.compare_digest(totp(secret, candidate), code):
            return candidate
    return None
