from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import EmailVerification, Message, Token, UserCreate, UserLogin
from app.services.email import send_verification_email
from app.services.rate_limiter import can_send, record_send, remaining_seconds

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Message, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    token = create_access_token(subject=user_in.email)

    user = User(
        email=user_in.email,
        username=user_in.username,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        verification_token=token,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    background_tasks.add_task(send_verification_email, user_in.email, token)

    return {"message": "Registration successful. Please check your email to verify your account."}


@router.post("/login", response_model=Token)
def login(user_in: UserLogin, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox.",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    access_token = create_access_token(subject=user.email)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/verify-email", response_model=Message)
def verify_email(verification: EmailVerification, db: Session = Depends(get_db)) -> dict:
    email = decode_access_token(verification.token)
    if email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    user.is_verified = True
    user.verification_token = None
    db.commit()

    return {"message": "Email verified successfully. You can now log in."}


@router.get("/verify-email", response_model=Message)
def verify_email_get(token: str, db: Session = Depends(get_db)) -> dict:
    email = decode_access_token(token)
    if email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    user.is_verified = True
    user.verification_token = None
    db.commit()

    return {"message": "Email verified successfully. You can now log in."}


@router.post("/resend-verification", response_model=Message)
def resend_verification(user_in: UserLogin, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified")

    if not can_send(user.email):
        remaining = remaining_seconds(user.email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting another verification email.",
        )

    new_token = create_access_token(subject=user.email)
    user.verification_token = new_token
    db.commit()

    if not send_verification_email(user.email, new_token):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email",
        )

    record_send(user.email)

    return {"message": "Verification email resent. Please check your inbox."}
