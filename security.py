import base64
import hashlib
import hmac
import os
from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    raw = os.getenv("ENCRYPTION_KEY", "development-only-change-me").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return "[contenuto non decifrabile]"


def valid_password(candidate: str) -> bool:
    expected = os.getenv("APP_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(candidate, expected)
