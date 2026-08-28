"""Personal (single-owner) account auth.

The verification code is stored bcrypt-hashed, expires after 15 minutes and is
limited to ``MAX_OTP_ATTEMPTS`` wrong attempts before a resend is required —
matching the hardening applied to organisation accounts.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import user_cache, user_list_cache
from app.core.security import (
    MAX_OTP_ATTEMPTS,
    create_access_token,
    generate_otp,
    get_otp_expiry,
    get_password_hash,
    hash_otp,
    otp_is_expired,
    otp_matches,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import EmailResend, EmailVerificationOTP, Message, Token, UserCreate, UserLogin
from app.services.email import send_verification_email
from app.services.rate_limiter import blocked_seconds, can_send, record_send, remaining_seconds

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_user_by_email(email: str, db: Session) -> User | None:
    cache_key = f"user_email:{email}"
    cached = user_cache.get(cache_key)
    if cached is not None:
        return cached
    user = db.query(User).filter(User.email == email).first()
    if user:
        user_cache[cache_key] = user
    return user


def _cache_user(user: User) -> None:
    user_cache[f"user_email:{user.email}"] = user
    user_cache[f"user_id:{user.id}"] = user


@router.post("/register", response_model=Message, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    existing = _get_user_by_email(user_in.email, db)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    otp = generate_otp()

    user = User(
        email=user_in.email,
        username=user_in.username,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        verification_otp=hash_otp(otp),
        verification_otp_expires_at=get_otp_expiry(),
        is_verified=False,
        otp_attempts=0,
    )
    db.add(user)
    db.commit()
    _cache_user(user)
    user_list_cache.pop("all", None)

    background_tasks.add_task(send_verification_email, user_in.email, otp)

    return {"message": "Registration successful. Please check your email for the verification code."}


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)) -> dict:
    user = _get_user_by_email(user_in.email, db)
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # if not user.is_verified:
    #     if blocked := blocked_seconds(user.email):
    #         detail = (
    #             "Too many verification code requests. "
    #             f"This account is temporarily blocked — try again in {blocked} seconds."
    #         )
    #     elif can_send(user.email):
    #         otp = generate_otp()
    #         user.verification_otp = hash_otp(otp)
    #         user.verification_otp_expires_at = get_otp_expiry()
    #         user.otp_attempts = 0
    #         db.commit()
    #         _cache_user(user)
    #         send_verification_email(user.email, otp)
    #         record_send(user.email)
    #         detail = "Email not verified. A new verification code has been sent to your email."
    #     else:
    #         detail = (
    #             "Email not verified. A verification code was sent recently — "
    #             f"check your inbox or wait {remaining_seconds(user.email)}s to request a new one."
    #         )
    #     raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS if blocked else status.HTTP_403_FORBIDDEN, detail=detail)

    if not user.is_active: # type:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    access_token = create_access_token(subject=user.email, claims={"typ": "user"})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/verify-email", response_model=Message)
def verify_email(verification: EmailVerificationOTP, db: Session = Depends(get_db)) -> dict:
    user = _get_user_by_email(verification.email, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    if user.otp_attempts >= MAX_OTP_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Request a new verification code.",
        )

    if otp_is_expired(user.verification_otp_expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Request a new one.",
        )

    if not otp_matches(verification.otp, user.verification_otp):
        user.otp_attempts += 1
        db.commit()
        _cache_user(user)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    user.is_verified = True
    user.verification_otp = None
    user.verification_otp_expires_at = None
    user.otp_attempts = 0
    db.commit()
    _cache_user(user)

    return {"message": "Email verified successfully. You can now log in."}


@router.post("/resend-verification", response_model=Message)
def resend_verification(user_in: EmailResend, db: Session = Depends(get_db)) -> dict:
    user = _get_user_by_email(user_in.email, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    if blocked := blocked_seconds(user.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many verification code requests. "
                f"This account is temporarily blocked — try again in {blocked} seconds."
            ),
        )

    if not can_send(user.email):
        remaining = remaining_seconds(user.email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting another verification code.",
        )

    new_otp = generate_otp()
    user.verification_otp = hash_otp(new_otp)
    user.verification_otp_expires_at = get_otp_expiry()
    user.otp_attempts = 0
    db.commit()
    _cache_user(user)

    if not send_verification_email(user.email, new_otp):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email",
        )

    record_send(user.email)

    return {"message": "Verification code resent. Please check your inbox."}
