"""Organisation admin operations: settings, member management, and the transparency
feed that replaces the frontend's in-browser notification store."""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import require_manager, require_owner
from app.models.organisation import Organisation, OrgMember
from app.services.org_user import invite_member

# Roles the frontend's permission map allows to be assigned at the backend too.
# The three department-manager variants are stored as-is and normalised to the
# generic "manager" role for permission checks (see core/permissions.py).
ASSIGNABLE_ROLES = (
    "super-admin",
    "admin",
    "manager",
    "hrm-manager",
    "finance-manager",
    "logistics-manager",
    "staff",
    "external",
)
PER_PAGE = 20


# --------------------------------------------------------------------------- #
# Organisation settings
# --------------------------------------------------------------------------- #
def get_org_public(org: Organisation) -> dict[str, Any]:
    return {
        "id": org.id,
        "name": org.name,
        "businessEmail": org.business_email,
        "verified": org.is_verified,
    }


def get_org_settings(db: Session, org: Organisation, member: OrgMember) -> dict[str, Any]:
    require_manager(member)
    member_count = db.query(func.count(OrgMember.id)).filter(OrgMember.org_id == org.id).scalar() or 0
    return {
        "name": org.name,
        "business_email": org.business_email,
        "member_count": member_count,
    }


def update_org_settings(
    db: Session, org: Organisation, member: OrgMember, name: str | None, business_email: str | None
) -> dict[str, Any]:
    require_owner(member)
    if name:
        clash = db.query(Organisation).filter(Organisation.name == name, Organisation.id != org.id).first()
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Another organisation already uses this name"
            )
        org.name = name
    if business_email and business_email.lower() != org.business_email.lower():
        clash = (
            db.query(Organisation)
            .filter(Organisation.business_email == business_email.lower(), Organisation.id != org.id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Another organisation already uses this email"
            )
        org.business_email = business_email.lower()
    db.commit()
    db.refresh(org)
    return get_org_settings(db, org, member)


# --------------------------------------------------------------------------- #
# Member management
# --------------------------------------------------------------------------- #
def list_members(
    db: Session, org: Organisation, member: OrgMember, search: str | None = None, page: int = 1
) -> dict[str, Any]:
    query = db.query(OrgMember).filter(OrgMember.org_id == org.id)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(
            OrgMember.email.ilike(like) | OrgMember.full_name.ilike(like) | OrgMember.username.ilike(like)
        )
    total = query.count()
    rows = query.order_by(OrgMember.created_at).offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    return {
        "members": [m.as_api for m in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PER_PAGE)),
    }


def add_member(
    db: Session, org: Organisation, member: OrgMember, email: str, role: str, job_title: str | None
) -> dict[str, Any]:
    require_manager(member)
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    created = invite_member(db, org, email, role, job_title)
    return created.as_api


def update_member_profile(
    db: Session,
    org: Organisation,
    member: OrgMember,
    target_id: str,
    *,
    name: str | None = None,
    email: str | None = None,
    username: str | None = None,
    phone: str | None = None,
    job_title: str | None = None,
) -> dict[str, Any]:
    """Edit a member's profile fields (never the password or the role)."""
    require_manager(member)
    target = db.query(OrgMember).filter(OrgMember.id == target_id, OrgMember.org_id == org.id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target.role == "super-admin" and member.id != target.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can manage the owner")
    if name is not None:
        target.full_name = name
    if email is not None and email.lower() != target.email:
        clash = (
            db.query(OrgMember)
            .filter(OrgMember.org_id == org.id, OrgMember.email == email.lower(), OrgMember.id != target.id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another member already uses this email")
        target.email = email.lower()
    if username is not None and username != target.username:
        clash = (
            db.query(OrgMember)
            .filter(OrgMember.org_id == org.id, OrgMember.username == username, OrgMember.id != target.id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Another member already uses this username"
            )
        target.username = username
    if phone is not None:
        target.phone = phone
    if job_title is not None:
        target.job_title = job_title
    db.commit()
    db.refresh(target)
    return target.as_api


def update_member_role(db: Session, org: Organisation, member: OrgMember, target_id: str, role: str) -> dict[str, Any]:
    require_manager(member)
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    target = db.query(OrgMember).filter(OrgMember.id == target_id, OrgMember.org_id == org.id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target.role == "super-admin" and member.role != "super-admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can manage the owner")
    target.role = role
    db.commit()
    db.refresh(target)
    return target.as_api


def update_member_status(
    db: Session,
    org: Organisation,
    member: OrgMember,
    target_id: str,
    *,
    disabled: bool | None = None,
    is_active: bool | None = None,
    data_blocked: bool | None = None,
) -> dict[str, Any]:
    require_manager(member)
    target = db.query(OrgMember).filter(OrgMember.id == target_id, OrgMember.org_id == org.id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target.role == "super-admin" and member.id != target.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can manage the owner")
    if disabled is not None:
        target.disabled = disabled
    if is_active is not None:
        target.is_active = is_active
    if data_blocked is not None:
        target.data_blocked = data_blocked
    db.commit()
    db.refresh(target)
    return target.as_api


def delete_member(db: Session, org: Organisation, member: OrgMember, target_id: str) -> None:
    require_owner(member)
    target = db.query(OrgMember).filter(OrgMember.id == target_id, OrgMember.org_id == org.id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if target.id == member.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own account")
    if target.role == "super-admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the owner")
    db.delete(target)
    db.commit()


def get_member_profile(db: Session, org: Organisation, member: OrgMember, target_id: str) -> dict[str, Any]:
    target = db.query(OrgMember).filter(OrgMember.id == target_id, OrgMember.org_id == org.id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return target.as_api
