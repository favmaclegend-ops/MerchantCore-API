"""Organisation account lifecycle: registration, verification, login, invites.

Orgs follow the exact same hardening as personal accounts — a six-digit code
that is stored bcrypt-hashed, expires after 15 minutes, and caps at 5 failed
attempts before forcing a new code. The org must be verified before any member
(including the creator) can log in.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
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
from app.models.organisation import Organisation, OrgMember
from app.services.email import send_email

# Org owners may send a limited number of invite codes per day.
INVITE_CODE_LIFETIME_DAYS = 7


# --------------------------------------------------------------------------- #
# Registration / verification
# --------------------------------------------------------------------------- #
def create_organisation(
    db: Session, name: str, business_email: str, username: str, full_name: str, password: str
) -> Organisation:
    if db.query(Organisation).filter(Organisation.business_email == business_email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An organisation with this email already exists"
        )
    if db.query(Organisation).filter(Organisation.name == name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An organisation with this name already exists"
        )

    org = Organisation(
        name=name,
        business_email=business_email,
        verification_otp=None,
    )
    db.add(org)
    db.flush()

    member = OrgMember(
        org_id=org.id,
        email=business_email,
        username=username,
        full_name=full_name,
        role="super-admin",
        job_title="Owner",
        hashed_password=get_password_hash(password),
        is_verified=False,
    )
    db.add(member)
    db.commit()
    db.refresh(org)
    db.refresh(member)

    send_org_verification_code(db, org)
    return org


def send_org_verification_code(db: Session, org: Organisation) -> None:
    if org.is_verified:
        return
    code = generate_otp()
    org.verification_otp = hash_otp(code)
    org.verification_otp_expires_at = get_otp_expiry()
    org.otp_attempts = 0
    db.commit()
    db.refresh(org)
    send_email(
        to_email=org.business_email,
        subject=f"Verify your organisation: {org.name}",
        html=f"<p>Your organisation verification code is <b>{code}</b>. It expires in 15 minutes.</p>",
    )


def verify_organisation(db: Session, org: Organisation, code: str) -> dict:
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
    db.refresh(org)
    return {"message": "Organisation verified successfully. You can now log in."}


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
def login_organisation(db: Session, email: str, password: str) -> dict:
    member = db.query(OrgMember).filter(OrgMember.email == email).first()

    if not member:
        org = db.query(Organisation).filter(Organisation.business_email == email).first()
        if org:
            member = db.query(OrgMember).filter(
                OrgMember.org_id == org.id, OrgMember.role == "super-admin"
            ).first()

    if not member:
        print('No Member')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if member.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been disabled. Contact your administrator."
        )
    if not member.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been blocked. Contact your administrator."
        )
    if not verify_password(password, member.hashed_password):
          
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    org = db.query(Organisation).filter(Organisation.id == member.org_id).first()

    if not org or not org.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organisation has not been verified. Check your inbox for the verification code.",
        )

    token = create_access_token(subject=member.id, claims={"typ": "member", "org_id": member.org_id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "member_id": member.id,
        "role": member.role,
        "full_name": member.full_name,
        "username": member.username,
        "email": member.email,
        "org_id": member.org_id,
        "org_name": org.name,
    }


# --------------------------------------------------------------------------- #
# Invites
# --------------------------------------------------------------------------- #
def invite_member(db: Session, org: Organisation, email: str, role: str, job_title: str | None, password: str | None = None) -> OrgMember:
    if email.lower() == org.business_email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="That is the owner email and cannot be invited as a member"
        )

    existing = db.query(OrgMember).filter(OrgMember.org_id == org.id, OrgMember.email == email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A member with this email already exists")

    raw_password = password if password else generate_otp() + generate_otp()
    member = OrgMember(
        org_id=org.id,
        email=email.lower(),
        username=email.lower().split("@")[0],
        full_name=email.lower().split("@")[0],
        role=role,
        job_title=job_title,
        hashed_password=get_password_hash(raw_password),
        is_verified=False,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    invite_link = f"{settings.FRONTEND_URL}/login"
    send_email(
        to_email=email,
        subject=f"You've been invited to {org.name}",
        html=(
            f"<p>You've been invited to join <b>{org.name}</b> as <b>{role}</b>.</p>"
            f"<p>Log in at <a href='{invite_link}'>{invite_link}</a> using this email.</p>"
        ),
    )
    return member
