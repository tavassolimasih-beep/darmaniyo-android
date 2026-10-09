import os
import datetime
import hashlib
import hmac
import secrets
from typing import Optional, Iterable

try:
    import bcrypt  # در گوشی (Termux) ممکن است نصب نباشد؛ در این حالت از PBKDF2 استفاده می‌شود
except ImportError:
    bcrypt = None
from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

COOKIE_NAME = "access_token"


def _to_bcrypt_bytes(password: str) -> bytes:
    # bcrypt فقط تا ۷۲ بایت رو پردازش می‌کنه؛ برای امنیت بیشتر رمزهای خیلی بلند رو کوتاه می‌کنیم
    return password.encode("utf-8")[:72]


_PBKDF2_PREFIX = "pbkdf2_sha256"
_PBKDF2_ROUNDS = 200_000


def _pbkdf2(password: str, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)


def hash_password(password: str) -> str:
    if bcrypt is not None:
        hashed = bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt())
        return hashed.decode("utf-8")
    salt = secrets.token_bytes(16)
    return f"{_PBKDF2_PREFIX}${_PBKDF2_ROUNDS}${salt.hex()}${_pbkdf2(password, salt, _PBKDF2_ROUNDS).hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith(_PBKDF2_PREFIX + "$"):
            _, rounds, salt_hex, hash_hex = hashed_password.split("$")
            calc = _pbkdf2(plain_password, bytes.fromhex(salt_hex), int(rounds))
            return hmac.compare_digest(calc.hex(), hash_hex)
        if bcrypt is None:
            return False
        return bcrypt.checkpw(_to_bcrypt_bytes(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    payload = decode_access_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    user = db.query(models.User).filter(models.User.id == payload["user_id"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "user_id" not in payload:
        return None
    return db.query(models.User).filter(models.User.id == payload["user_id"]).first()


def require_roles(*roles: Iterable[str]):
    """وابستگی برای محدود کردن دسترسی به یک یا چند نقش خاص"""
    allowed = {r.value if hasattr(r, "value") else r for r in roles}

    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role.value not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="دسترسی غیرمجاز")
        return user

    return checker
