from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    default="pbkdf2_sha256",
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _create_token(data: dict[str, Any], secret: str, expires_delta: timedelta) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    payload.update({"exp": expire})
    return jwt.encode(payload, secret, algorithm="HS256")


def create_access_token(subject: str) -> str:
    return _create_token({"sub": subject, "type": "access"}, settings.jwt_secret_key, timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(subject: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    token = _create_token({"sub": subject, "type": "refresh"}, settings.jwt_refresh_secret_key, timedelta(days=settings.refresh_token_expire_days))
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    return _decode_token(token, settings.jwt_secret_key, "access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    return _decode_token(token, settings.jwt_refresh_secret_key, "refresh")


def _decode_token(token: str, secret: str, token_type: str) -> dict[str, Any]:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as exc:
        raise credentials_error from exc
    if payload.get("type") != token_type or not payload.get("sub"):
        raise credentials_error
    return payload
