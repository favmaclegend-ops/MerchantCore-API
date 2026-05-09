from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import user_cache, user_list_cache
from app.core.security import create_access_token, generate_otp, get_otp_expiry, get_password_hash, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import EmailVerificationOTP, Message, Token, UserCreate, UserLogin
from app.services.email import send_verification_email
from app.services.rate_limiter import can_send, record_send, remaining_seconds

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
        verification_otp=otp,
        verification_otp_expires_at=get_otp_expiry(),
        is_verified=False,
    )
    db.add(user)
    db.commit()
    user_cache[f"user_email:{user.email}"] = user
    user_cache[f"user_id:{user.id}"] = user
    user_list_cache.pop("all", None)

    background_tasks.add_task(send_verification_email, user_in.email, otp)

    return {"message": "Registration successful. Please check your email for the verification code."}


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)) -> dict:
    user = _get_user_by_email(user_in.email, db)
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox for the verification code.",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    access_token = create_access_token(subject=user.email)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/verify-email", response_model=Message)
def verify_email(verification: EmailVerificationOTP, db: Session = Depends(get_db)) -> dict:
    from datetime import UTC, datetime

    user = _get_user_by_email(verification.email, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    if not user.verification_otp or user.verification_otp != verification.otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    if not user.verification_otp_expires_at or user.verification_otp_expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired")

    user.is_verified = True
    user.verification_otp = None
    user.verification_otp_expires_at = None
    db.commit()
    user_cache[f"user_email:{user.email}"] = user
    user_cache[f"user_id:{user.id}"] = user

    return {"message": "Email verified successfully. You can now log in."}


@router.post("/resend-verification", response_model=Message)
def resend_verification(user_in: UserLogin, db: Session = Depends(get_db)) -> dict:
    user = _get_user_by_email(user_in.email, db)
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    if not can_send(user.email):
        remaining = remaining_seconds(user.email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting another verification code.",
        )

    new_otp = generate_otp()
    user.verification_otp = new_otp
    user.verification_otp_expires_at = get_otp_expiry()
    db.commit()
    user_cache[f"user_email:{user.email}"] = user
    user_cache[f"user_id:{user.id}"] = user

    if not send_verification_email(user.email, new_otp):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email",
        )

    record_send(user.email)

    return {"message": "Verification code resent. Please check your inbox."}
