"""Security primitives: password hashing, JWT tokens, OTP codes and auth deps.

Two kinds of account exist and each gets a distinct token subject so one backend
serves both without ambiguity:

- Personal users: ``sub`` = email, claim ``typ`` = ``"user"``.
- Organisation members: ``sub`` = member id, claim ``typ`` = ``"member"`` plus
  ``org_id`` so every downstream query can be scoped to the right tenant.
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import user_cache
from app.db.session import get_db
from app.models.organisation import Organisation, OrgMember
from app.models.user import User

ALGORITHM = "HS256"
OTP_EXPIRE_MINUTES = 15
MAX_OTP_ATTEMPTS = 5
QR_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _fernet() -> Fernet:
    """A Fernet key derived from the app secret so QR tokens are authenticated
    and confidential (the raw order id never appears in the QR payload)."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(payload: str) -> str:
    """Encrypt an opaque token string for use in a scan-to-complete QR code."""
    return _fernet().encrypt(payload.encode("utf-8")).decode("utf-8")


def decrypt_token(token: str, max_age_seconds: int = QR_TOKEN_TTL_SECONDS) -> str:
    """Decrypt a QR token, rejecting anything tampered with or expired."""
    try:
        payload = _fernet().decrypt(token.encode("utf-8"), ttl=max_age_seconds)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code")
    return payload.decode("utf-8")



# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_access_token(subject: str, claims: dict | None = None, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.TOKEN_EXPIRE_MINUTES))
    to_encode: dict = {"exp": expire, "sub": subject, **(claims or {})}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def _extract_bearer(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")
    return authorization.replace("Bearer ", "", 1)


# --------------------------------------------------------------------------- #
# OTP codes (stored hashed, attempt-limited, expiring)
# --------------------------------------------------------------------------- #
def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return bcrypt.hashpw(otp.encode("utf-8"), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


def otp_matches(otp: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(otp.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def get_otp_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=OTP_EXPIRE_MINUTES)


def otp_is_expired(stored: datetime | None) -> bool:
    if stored is None:
        return True
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=UTC)
    return stored < datetime.now(UTC)


def verify_otp(otp: str, stored_hash: str | None, expires_at: datetime | None) -> tuple[bool, str]:
    """Validate a submitted code against its hash/expiry. Returns (ok, error)."""
    if otp_is_expired(expires_at):
        return False, "Verification code has expired. Request a new one."
    if not otp_matches(otp, stored_hash):
        return False, "Invalid verification code."
    return True, ""


# --------------------------------------------------------------------------- #
# Auth dependencies
# --------------------------------------------------------------------------- #
def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(_extract_bearer(authorization))
    if payload is None or payload.get("typ") not in (None, "user"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    cache_key = f"user_email:{email}"
    cached = user_cache.get(cache_key)
    if cached is not None:
        return cached
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_cache[cache_key] = user
    return user


def get_current_member(authorization: str = Header(...), db: Session = Depends(get_db)) -> OrgMember:
    payload = decode_access_token(_extract_bearer(authorization))
    if payload is None or payload.get("typ") != "member":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    member_id = payload.get("sub")
    org_id = payload.get("org_id")
    if not member_id or not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    member = db.query(OrgMember).filter(OrgMember.id == member_id, OrgMember.org_id == org_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if member.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been disabled. Contact your administrator."
        )
    if not member.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been blocked. Contact your administrator."
        )
    return member


def get_current_org(member: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)) -> Organisation:
    org = db.query(Organisation).filter(Organisation.id == member.org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    return org


def ensure_org_matches(member: OrgMember, org_id: str) -> None:
    """Guard used by org-scoped routes so a token can never read another tenant."""
    if member.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this organization")
