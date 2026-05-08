import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"
OTP_EXPIRE_MINUTES = 15


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.TOKEN_EXPIRE_MINUTES))
    to_encode = {"exp": expire, "sub": subject}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def get_otp_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=OTP_EXPIRE_MINUTES)
