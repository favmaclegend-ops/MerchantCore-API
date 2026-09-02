"""Public organisation auth: registration, verification, login, resend.

These routes are intentionally token-free. Registration creates the organisation
and its Super Admin member, then emails a hashed, expiring verification code.
No member (including the creator) can log in until the organisation is verified.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    MAX_OTP_ATTEMPTS,
    generate_otp,
    get_otp_expiry,
    get_password_hash,
    hash_otp,
    otp_is_expired,
    otp_matches,
)
from app.db.session import get_db
from app.models.organisation import Organisation, OrgMember
from app.services.email import EmailNotConfiguredError, send_email
from app.services.org_user import login_organisation
from app.services.rate_limiter import can_send, record_send, remaining_seconds

router = APIRouter(prefix="/auth/org", tags=["organisation auth"])


def _get_org_by_email(email: str, db: Session) -> Organisation | None:
    return db.query(Organisation).filter(Organisation.business_email == email.lower()).first()


def _get_org_by_member_email(email: str, db: Session) -> Organisation | None:
    """Look up an org via a member's email (e.g. super admin personal email)."""
    member = db.query(OrgMember).filter(OrgMember.email == email.lower()).first()
    if not member:
        return None
    return db.query(Organisation).filter(Organisation.id == member.org_id).first()


def _get_member_by_email(email: str, db: Session) -> OrgMember | None:
    return db.query(OrgMember).filter(OrgMember.email == email.lower()).first()


def _send_code_email(email: str, code: str, org_name: str) -> bool:
    return send_email(
        to_email=email,
        subject=f"Verify your organisation: {org_name}",
        html=(
            "<p>Your organisation verification code is:</p>"
            f"<h2 style='letter-spacing: 8px; font-size: 32px; text-align: center;'>{code}</h2>"
            "<p>Enter this code to verify your organisation's email address.</p>"
            "<p>This code will expire in 15 minutes.</p>"
        ),
    )


def _deliver_org_code(email: str, code: str, org_name: str) -> None:
    """Send the org verification email, surfacing failures as a clear 500."""
    try:
        _send_code_email(email, code, org_name)
    except EmailNotConfiguredError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email is not configured ({e}). Ask the admin to set RESEND_API_KEY or SMTP credentials.",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send the verification code to {email}. Please try again. ({e})",
        ) from e


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register_org(
    body: dict,
    db: Session = Depends(get_db),
) -> dict:
    name = (body.get("name") or "").strip()
    business_email = (body.get("business_email") or body.get("businessEmail") or "").strip().lower()
    super_admin_email = (body.get("super_admin_email") or body.get("superAdminEmail") or "").strip().lower()
    username = (body.get("username") or "").strip()
    full_name = (body.get("full_name") or body.get("fullName") or "").strip()
    password = body.get("password") or ""

    if not name or not business_email or not full_name or len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name, business email, full name and a password of at least 8 characters are required",
        )

    if not super_admin_email:
        super_admin_email = business_email

    if _get_org_by_email(business_email, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An organisation with this email already exists"
        )

    code = generate_otp()
    org = Organisation(
        name=name,
        business_email=business_email,
        verification_otp=hash_otp(code),
        verification_otp_expires_at=get_otp_expiry(),
        otp_attempts=0,
    )
    db.add(org)
    db.flush()

    member = OrgMember(
        org_id=org.id,
        email=super_admin_email,
        username=username or super_admin_email.split("@")[0],
        full_name=full_name,
        role="super-admin",
        job_title="Owner",
        hashed_password=get_password_hash(password),
        is_verified=False,
    )
    db.add(member)
    db.commit()
    db.refresh(org)

    _deliver_org_code(super_admin_email, code, name)
    return {
        "message": "Organisation registered. Check your email for the verification code.",
        "org_id": org.id,
    }


@router.post("/verify-email", response_model=dict)
def verify_org_email(body: dict, db: Session = Depends(get_db)) -> dict:
    email = (body.get("email") or "").strip().lower()
    code = body.get("otp") or body.get("code") or ""

    org = _get_org_by_member_email(email, db) or _get_org_by_email(email, db)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    if org.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organisation is already verified")
    if org.otp_attempts >= MAX_OTP_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Request a new verification code.",
        )
    if otp_is_expired(org.verification_otp_expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired. Request a new one."
        )
    if not otp_matches(code, org.verification_otp):
        org.otp_attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    org.is_verified = True
    org.verification_otp = None
    org.verification_otp_expires_at = None
    org.otp_attempts = 0
    creator = db.query(OrgMember).filter(OrgMember.org_id == org.id, OrgMember.role == "super-admin").first()
    if creator:
        creator.is_verified = True
    db.commit()
    return {"message": "Organisation verified successfully. You can now log in."}


@router.post("/resend-verification", response_model=dict)
def resend_org_code(body: dict, db: Session = Depends(get_db)) -> dict:
    email = (body.get("email") or "").strip().lower()
    org = _get_org_by_member_email(email, db) or _get_org_by_email(email, db)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    if org.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organisation is already verified")

    admin_member = db.query(OrgMember).filter(
        OrgMember.org_id == org.id, OrgMember.role == "super-admin"
    ).first()
    admin_email = admin_member.email if admin_member else email

    if not can_send(f"org:{org.id}"):
        remaining = remaining_seconds(f"org:{org.id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting another verification code.",
        )

    code = generate_otp()
    org.verification_otp = hash_otp(code)
    org.verification_otp_expires_at = get_otp_expiry()
    org.otp_attempts = 0
    db.commit()

    _deliver_org_code(admin_email, code, org.name)
    record_send(f"org:{org.id}")
    return {"message": "Verification code resent. Please check your inbox."}


@router.post("/login", response_model=dict)
def org_login(body: dict, db: Session = Depends(get_db)) -> dict:
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    return login_organisation(db, email, password)
