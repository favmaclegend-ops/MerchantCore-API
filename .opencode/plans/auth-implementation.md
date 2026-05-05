# Authentication Implementation Plan

## Overview
Email-based signup/login with Gmail SMTP verification, JWT access tokens, password min 8 chars, 60s resend cooldown.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/auth/signup` | No | Create user, send verification email |
| `POST` | `/api/v1/auth/login` | No | Authenticate (blocks if unverified) |
| `GET` | `/api/v1/auth/verify` | No | Verify email via token query param |
| `POST` | `/api/v1/auth/resend-verification` | No | Resend verification email (60s cooldown) |
| `GET/POST/PATCH/DELETE` | `/api/v1/users/*` | Yes | CRUD (requires Bearer token) |

---

## 1. `pyproject.toml` — Updated Dependencies

```toml
[project]
name = "merchant-core-api"
version = "0.1.0"
description = "Merchant Core API Service"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.136.1",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy>=2.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pydantic[email]",
    "passlib[bcrypt]>=1.7.4",
    "python-jose[cryptography]>=3.3.0",
    "email-validator>=2.0.0",
    "aiosmtplib>=3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.28.0",
    "ruff>=0.9.0",
]

[tool.ruff]
line-length = 120
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

## 2. `.env` (to be created — NOT committed)

```
DATABASE_URL=sqlite:///./app.db
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=false
ALLOWED_HOSTS=["*"]
API_BASE_URL=http://localhost:8000

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=favmac007@gmail.com
SMTP_PASSWORD=ripu gtze nszx gkts
FROM_EMAIL=favmac007@gmail.com
```

---

## 3. `.env.example` — Updated

```
DATABASE_URL=sqlite:///./app.db
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=false
ALLOWED_HOSTS=["*"]
API_BASE_URL=http://localhost:8000

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
FROM_EMAIL=your-email@gmail.com
```

---

## 4. `app/config.py` — Updated with SMTP Settings

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    PROJECT_NAME: str = "Merchant Core API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Merchant Core API Service"

    DATABASE_URL: str = "sqlite:///./app.db"
    ALLOWED_HOSTS: list[str] = ["*"]

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = "noreply@merchant-core-api.com"

    API_BASE_URL: str = "http://localhost:8000"

    DEBUG: bool = False


settings = Settings()
```

---

## 5. `app/models/user.py` — Updated with Verification Fields

```python
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

---

## 6. `app/core/auth.py` — NEW (replaces security.py)

```python
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
VERIFICATION_TOKEN_EXPIRE_HOURS = 24


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_verification_token(user_id: str) -> str:
    return create_access_token(
        data={"sub": user_id, "type": "verification"},
        expires_delta=timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS),
    )


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
```

---

## 7. `app/schemas/auth.py` — NEW

```python
from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
```

---

## 8. `app/schemas/user.py` — Updated

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

---

## 9. `app/services/email_service.py` — NEW

```python
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings


async def send_verification_email(to_email: str, verification_token: str) -> bool:
    verification_link = f"{settings.API_BASE_URL}/api/v1/auth/verify?token={verification_token}"

    message = MIMEMultipart("alternative")
    message["Subject"] = "Verify your email - Merchant Core API"
    message["From"] = settings.FROM_EMAIL
    message["To"] = to_email

    text_body = f"""
Welcome to Merchant Core API!

Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you did not create an account, please ignore this email.
"""

    html_body = f"""
<html>
  <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <h2>Welcome to Merchant Core API!</h2>
    <p>Please verify your email address by clicking the button below:</p>
    <a href="{verification_link}"
       style="display: inline-block; padding: 12px 24px; background-color: #4F46E5;
              color: white; text-decoration: none; border-radius: 6px; margin: 16px 0;">
      Verify Email
    </a>
    <p>Or click this link: <a href="{verification_link}">{verification_link}</a></p>
    <p style="color: #666; font-size: 14px;">This link will expire in 24 hours.</p>
    <p style="color: #666; font-size: 14px;">If you did not create an account, please ignore this email.</p>
  </body>
</html>
"""

    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=False,
            start_tls=True,
        )
        return True
    except Exception:
        return False
```

---

## 10. `app/services/user_service.py` — NEW

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, create_verification_token, decode_token, get_password_hash, verify_password
from app.models.user import User
from app.services.email_service import send_verification_email


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def create_user(db: Session, email: str, password: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        verification_token="",
        verification_sent_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_verification_token(user.id)
    user.verification_token = token
    db.commit()
    db.refresh(user)

    return user


async def send_verification(user: User) -> bool:
    token = create_verification_token(user.id)

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        user.verification_token = token
        user.verification_sent_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

    return await send_verification_email(user.email, token)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def verify_email(db: Session, token: str) -> User | None:
    payload = decode_token(token)
    if not payload or payload.get("type") != "verification":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = get_user_by_id(db, user_id)
    if not user:
        return None
    if user.is_verified:
        return user

    user.is_verified = True
    user.verification_token = None
    db.commit()
    db.refresh(user)
    return user


def can_resend_verification(user: User) -> bool:
    if not user.verification_sent_at:
        return True
    cooldown = timedelta(seconds=60)
    return datetime.now(timezone.utc) - user.verification_sent_at >= cooldown
```

---

## 11. `app/routers/auth.py` — NEW

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, decode_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, Token
from app.schemas.user import UserResponse
from app.services.user_service import (
    authenticate_user,
    can_resend_verification,
    create_user,
    get_user_by_email,
    get_user_by_id,
    send_verification,
    verify_email,
)

router = APIRouter(tags=["auth"])


def get_current_user(token: str = Depends(OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/signup", status_code=201)
async def signup(signup_data: SignupRequest, db: Session = Depends(get_db)) -> dict:
    existing = get_user_by_email(db, signup_data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = create_user(db, signup_data.email, signup_data.password)
    await send_verification(user)

    return {"message": "Check your email to verify your account"}


@router.post("/login", response_model=Token)
def login(login_data: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")

    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/verify", response_model=dict)
def verify(token: str = Query(..., description="Verification token"), db: Session = Depends(get_db)) -> dict:
    user = verify_email(db, token)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    access_token = create_access_token(data={"sub": user.id})
    if user.is_verified:
        return {
            "message": "Email was already verified",
            "access_token": access_token,
            "token_type": "bearer",
        }

    return {
        "message": "Email verified successfully",
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/resend-verification", status_code=200)
async def resend_verification(email: str, db: Session = Depends(get_db)) -> dict:
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified")
    if not can_resend_verification(user):
        raise HTTPException(status_code=429, detail="Please wait 60 seconds before requesting another verification email")

    await send_verification(user)
    return {"message": "Verification email sent"}
```

---

## 12. `app/routers/users.py` — Updated (protected with auth)

All CRUD endpoints now require `current_user: User = Depends(get_current_user)`.

---

## 13. `app/main.py` — Updated

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from app.config import settings
from app.db.session import engine, Base
from app.routers import users, auth


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(users.router, prefix="/api/v1")

    return application


app = create_application()


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.on_event("shutdown")
async def shutdown() -> None:
    pass


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
```

---

## Implementation Order

1. Update `pyproject.toml` → `uv sync`
2. Update `app/config.py`
3. Update `app/models/user.py`
4. Create `app/core/auth.py` (replaces `security.py`)
5. Create `app/schemas/auth.py`
6. Update `app/schemas/user.py`
7. Create `app/services/email_service.py`
8. Create `app/services/user_service.py`
9. Create `app/routers/auth.py`
10. Update `app/routers/users.py`
11. Update `app/main.py`
12. Create `.env` (with your SMTP creds)
13. Update `.env.example`
14. Delete old `main.py` at project root

---

## Notes

- The `app/core/security.py` file will be **deleted** and replaced by `app/core/auth.py`
- Root `main.py` will be **deleted** since the app now lives at `app/main.py`
- Need to create a `.env` file (not committed) with your actual SMTP credentials
- The verification token is a JWT with 24h expiry, embedded in a clickable URL
- Login returns 403 if user is not verified
- Resend verification is rate-limited to once per 60 seconds via `verification_sent_at` timestamp
