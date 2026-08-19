from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
import jwt
from jwt import InvalidTokenError

from app.core.config import settings

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(value: str) -> str:
    return PASSWORDS.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    try:
        return PASSWORDS.verify(hashed, value)
    except (VerifyMismatchError, VerificationError):
        return False


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_token(size: int = 48) -> str:
    return secrets.token_urlsafe(size)


def create_access_token(subject: str, role: str) -> tuple[str, int]:
    expires = timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(timezone.utc)
    claims = {"sub": subject, "role": role, "typ": "access", "iat": now, "exp": now + expires, "jti": random_token(16)}
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(expires.total_seconds())


def decode_access_token(value: str) -> dict | None:
    try:
        claims = jwt.decode(value, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if claims.get("typ") != "access":
            return None
        return claims
    except InvalidTokenError:
        return None


def encrypt_secret(value: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.master_secret.encode()).digest())
    return Fernet(key).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.master_secret.encode()).digest())
    try:
        return Fernet(key).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("secret_decryption_failed") from exc


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
