"""Organisation HTTP API.

All organisation endpoints live under ``/api/v1/organisations`` and are locked by
a member token. Every ``/organisations/{org_id}/...`` route first confirms the
token belongs to that org, so cross-tenant access is structurally impossible.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_member, get_current_org
from app.db.session import get_db
from app.models.organisation import Organisation, OrgMember
from app.services import org_admin, org_notification, org_ui

router = APIRouter(prefix="/organisations", tags=["organisations"])

DbDep = Annotated[Session, Depends(get_db)]
MemberDep = Annotated[OrgMember, Depends(get_current_member)]
OrgDep = Annotated[Organisation, Depends(get_current_org)]


def _require_same_org(org_id: str, member: OrgMember) -> None:
    if member.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised for this organisation",
        )


def _member(org: Organisation, db: DbDep, member: MemberDep) -> tuple[Session, OrgMember]:
    _require_same_org(org.id, member)
    return db, member


# --------------------------------------------------------------------------- #
# Organisation settings
# --------------------------------------------------------------------------- #
@router.get("", response_model=dict)
def get_organisation(org: OrgDep, db: DbDep, member: MemberDep) -> dict:
    db, member = _member(org, db, member)
    return org_admin.get_org_public(org)


@router.get("/{org_id}/settings", response_model=dict)
def get_settings(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_admin.get_org_settings(db, org, member)


@router.patch("/{org_id}/settings", response_model=dict)
def patch_settings(
    org_id: str,
    body: Annotated[dict, Body()],
    db: DbDep,
    member: MemberDep,
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_admin.update_org_settings(db, org, member, body.get("name"), body.get("business_email"))


# --------------------------------------------------------------------------- #
# Members
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/members", response_model=dict)
def list_members(
    org_id: str,
    db: DbDep,
    member: MemberDep,
    search: str | None = None,
    page: int = Query(1, ge=1),
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_admin.list_members(db, org, member, search, page)


@router.post("/{org_id}/members", response_model=dict)
def add_member(
    org_id: str,
    body: Annotated[dict, Body()],
    db: DbDep,
    member: MemberDep,
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    print(member)
    email = (body.get("email") or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid email is required")
    return org_admin.add_member(db, org, member, email, body.get("role", "staff"), body.get("jobTitle"), body.get("password"))


@router.patch("/{org_id}/members/{member_id}/role", response_model=dict)
def change_member_role(
    org_id: str,
    member_id: str,
    body: Annotated[dict, Body()],
    db: DbDep,
    member: MemberDep,
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    print(member)
    
    return org_admin.update_member_role(db, org, member, member_id, body.get("role", "staff"))


@router.patch("/{org_id}/members/{member_id}", response_model=dict)
def update_member_profile(
    org_id: str,
    member_id: str,
    body: Annotated[dict, Body()],
    db: DbDep,
    member: MemberDep,
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)

    return org_admin.update_member_profile(
        db,
        org,
        member,
        member_id,
        name=body.get("name"),
        email=body.get("email"),
        username=body.get("username"),
        phone=body.get("phone"),
        job_title=body.get("jobTitle"),
        password=body.get("password"),
    )


@router.patch("/{org_id}/members/{member_id}/status", response_model=dict)
def change_member_status(
    org_id: str,
    member_id: str,
    body: Annotated[dict, Body()],
    db: DbDep,
    member: MemberDep,
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_admin.update_member_status(
        db,
        org,
        member,
        member_id,
        disabled=body.get("disabled"),
        is_active=body.get("isActive"),
        data_blocked=body.get("dataBlocked"),
    )


@router.get("/{org_id}/members/{member_id}", response_model=dict)
def member_profile(org_id: str, member_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_admin.get_member_profile(db, org, member, member_id)


@router.delete("/{org_id}/members/{member_id}", response_model=dict)
def remove_member(org_id: str, member_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    org_admin.delete_member(db, org, member, member_id)
    return {"message": "Member removed"}


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/notifications", response_model=dict)
def list_notifications(
    org_id: str,
    db: DbDep,
    member: MemberDep,
    kind: str | None = None,
    page: int = Query(1, ge=1),
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_notification.list_notifications(db, org, member, kind, page)


@router.get("/{org_id}/notifications/unread-count", response_model=dict)
def notification_unread_count(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return {"unread": org_notification.unread_count(db, org, member)}


@router.post("/{org_id}/notifications/{notification_id}/read", response_model=dict)
def mark_notification_read(org_id: str, notification_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_notification.mark_read(db, org, member, notification_id)


@router.post("/{org_id}/notifications/read-all", response_model=dict)
def mark_all_notifications_read(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    updated = org_notification.mark_all_read(db, org, member)
    return {"updated": updated}


@router.delete("/{org_id}/notifications/{notification_id}", response_model=dict)
def delete_notification(org_id: str, notification_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    org_notification.delete_notification(db, org, member, notification_id)
    return {"message": "Notification deleted"}


@router.delete("/{org_id}/notifications", response_model=dict)
def clear_notifications(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    deleted = org_notification.clear_all(db, org, member)
    return {"deleted": deleted}


@router.get("/{org_id}/notification-settings", response_model=dict)
def get_notification_settings(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_notification.get_settings(db, org, member)


@router.patch("/{org_id}/notification-settings", response_model=dict)
def patch_notification_settings(
    org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_notification.update_settings(db, org, member, body)


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/dashboard", response_model=dict)
def dashboard(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.org_dashboard(db, org, member)


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/products", response_model=dict)
def list_products(
    org_id: str,
    db: DbDep,
    member: MemberDep,
    search: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_products(db, org, member, search, category, page)


@router.get("/{org_id}/products/status-summary", response_model=dict)
def product_status_summary(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.get_product_status_summary(db, org, member)


@router.post("/{org_id}/products", response_model=dict)
def create_product(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    if not body.get("name") or not body.get("sku"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name and SKU are required")
    return org_ui.create_product(db, org, member, body)


@router.get("/{org_id}/products/{product_id}", response_model=dict)
def get_product(org_id: str, product_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.get_product(db, org, member, product_id)


@router.patch("/{org_id}/products/{product_id}", response_model=dict)
def update_product(org_id: str, product_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_product(db, org, member, product_id, body)


@router.delete("/{org_id}/products/{product_id}", response_model=dict)
def delete_product(org_id: str, product_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_product(db, org, member, product_id)


# --------------------------------------------------------------------------- #
# Customers & credit
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/customers", response_model=dict)
def list_customers(
    org_id: str,
    db: DbDep,
    member: MemberDep,
    search: str | None = None,
    page: int = Query(1, ge=1),
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_customers(db, org, member, search, page)


@router.post("/{org_id}/customers", response_model=dict)
def create_customer(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    if not body.get("name"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")
    return org_ui.create_customer(db, org, member, body)


@router.get("/{org_id}/customers/{customer_id}", response_model=dict)
def get_customer(org_id: str, customer_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.get_customer(db, org, member, customer_id)


@router.patch("/{org_id}/customers/{customer_id}", response_model=dict)
def update_customer(org_id: str, customer_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_customer(db, org, member, customer_id, body)


@router.delete("/{org_id}/customers/{customer_id}", response_model=dict)
def delete_customer(org_id: str, customer_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_customer(db, org, member, customer_id)


@router.get("/{org_id}/credit", response_model=list)
def list_credit(org_id: str, db: DbDep, member: MemberDep, search: str | None = None) -> list:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_credit_entries(db, org, member, search)


@router.get("/{org_id}/credit/summary", response_model=dict)
def credit_summary(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.credit_summary(db, org, member)


@router.post("/{org_id}/credit/{customer_id}/purchase", response_model=dict)
def credit_purchase(org_id: str, customer_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.record_credit_purchase(db, org, member, customer_id, float(body.get("amount", 0)), body.get("code"))


@router.post("/{org_id}/credit/{customer_id}/payment", response_model=dict)
def credit_payment(org_id: str, customer_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.make_credit_payment(db, org, member, customer_id, float(body.get("amount", 0)))


# --------------------------------------------------------------------------- #
# POS
# --------------------------------------------------------------------------- #
@router.post("/{org_id}/pos/checkout", response_model=dict)
def pos_checkout(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.checkout(
        db,
        org,
        member,
        body.get("items") or [],
        body.get("paymentMethod") or "cash",
        body.get("customerName"),
    )


@router.get("/{org_id}/transactions", response_model=dict)
def list_transactions(
    org_id: str,
    db: DbDep,
    member: MemberDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_transactions(db, org, member, page, per_page)


@router.post("/{org_id}/transactions/{transaction_id}/refund", response_model=dict)
def refund(org_id: str, transaction_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.refund_transaction(db, org, member, transaction_id)


# --------------------------------------------------------------------------- #
# HRM
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/employees", response_model=dict)
def list_employees(
    org_id: str,
    db: DbDep,
    member: MemberDep,
    department: str | None = None,
    search: str | None = None,
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_employees(db, org, member, department, search)


@router.post("/{org_id}/employees", response_model=dict)
def create_employee(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    if not body.get("name"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")
    return org_ui.create_employee(db, org, member, body)


@router.get("/{org_id}/employees/{employee_id}", response_model=dict)
def get_employee(org_id: str, employee_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.get_employee(db, org, member, employee_id)


@router.patch("/{org_id}/employees/{employee_id}", response_model=dict)
def update_employee(org_id: str, employee_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_employee(db, org, member, employee_id, body)


@router.delete("/{org_id}/employees/{employee_id}", response_model=dict)
def delete_employee(org_id: str, employee_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_employee(db, org, member, employee_id)


@router.get("/{org_id}/benefits", response_model=list)
def list_benefits(org_id: str, db: DbDep, member: MemberDep) -> list:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_benefits(db, org, member)


@router.post("/{org_id}/benefits", response_model=dict)
def create_benefit(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_benefit(db, org, member, body)


@router.patch("/{org_id}/benefits/{benefit_id}", response_model=dict)
def update_benefit(org_id: str, benefit_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_benefit(db, org, member, benefit_id, body)


@router.delete("/{org_id}/benefits/{benefit_id}", response_model=dict)
def delete_benefit(org_id: str, benefit_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_benefit(db, org, member, benefit_id)


@router.post("/{org_id}/payroll/generate", response_model=dict)
def generate_payroll(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    period = (body.get("period") or "").strip()
    if not period:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Period is required")
    return org_ui.generate_payroll(db, org, member, period)


@router.get("/{org_id}/payroll", response_model=dict)
def list_payroll(org_id: str, db: DbDep, member: MemberDep, period: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_payroll(db, org, member, period)


@router.post("/{org_id}/payroll/{run_id}/paid", response_model=dict)
def mark_payroll_paid(org_id: str, run_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.mark_payroll_paid(db, org, member, run_id)


@router.delete("/{org_id}/payroll/{run_id}", response_model=dict)
def delete_payroll(org_id: str, run_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_payroll(db, org, member, run_id)


@router.get("/{org_id}/time-entries", response_model=dict)
def list_time_entries(org_id: str, db: DbDep, member: MemberDep, employee_id: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_time_entries(db, org, member, employee_id)


@router.post("/{org_id}/time-entries", response_model=dict)
def create_time_entry(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_time_entry(db, org, member, body)


@router.delete("/{org_id}/time-entries/{entry_id}", response_model=dict)
def delete_time_entry(org_id: str, entry_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_time_entry(db, org, member, entry_id)


@router.get("/{org_id}/attendance", response_model=dict)
def list_attendance(
    org_id: str, db: DbDep, member: MemberDep, date: str | None = None, employee_id: str | None = None
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_attendance(db, org, member, date, employee_id)


@router.post("/{org_id}/attendance/check-in", response_model=dict)
def check_in(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.check_in(db, org, member, body.get("employeeId"), body.get("date"))


@router.get("/{org_id}/reviews", response_model=dict)
def list_reviews(org_id: str, db: DbDep, member: MemberDep, employee_id: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_reviews(db, org, member, employee_id)


@router.post("/{org_id}/reviews", response_model=dict)
def create_review(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_review(db, org, member, body)


@router.post("/{org_id}/reviews/{review_id}/complete", response_model=dict)
def complete_review(org_id: str, review_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.complete_review(db, org, member, review_id)


@router.delete("/{org_id}/reviews/{review_id}", response_model=dict)
def delete_review(org_id: str, review_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_review(db, org, member, review_id)


# --------------------------------------------------------------------------- #
# Supply chain
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/suppliers", response_model=dict)
def list_suppliers(org_id: str, db: DbDep, member: MemberDep, search: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_suppliers(db, org, member, search)


@router.post("/{org_id}/suppliers", response_model=dict)
def create_supplier(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    if not body.get("name"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")
    return org_ui.create_supplier(db, org, member, body)


@router.patch("/{org_id}/suppliers/{supplier_id}", response_model=dict)
def update_supplier(org_id: str, supplier_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_supplier(db, org, member, supplier_id, body)


@router.delete("/{org_id}/suppliers/{supplier_id}", response_model=dict)
def delete_supplier(org_id: str, supplier_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_supplier(db, org, member, supplier_id)


@router.get("/{org_id}/purchase-orders", response_model=dict)
def list_purchase_orders(org_id: str, db: DbDep, member: MemberDep, status: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_purchase_orders(db, org, member, status)


@router.post("/{org_id}/purchase-orders", response_model=dict)
def create_purchase_order(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_purchase_order(db, org, member, body.get("supplierId"), body.get("items") or [])


@router.post("/{org_id}/purchase-orders/{order_id}/receive", response_model=dict)
def receive_purchase_order(org_id: str, order_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.receive_purchase_order(db, org, member, order_id)


@router.delete("/{org_id}/purchase-orders/{order_id}", response_model=dict)
def delete_purchase_order(org_id: str, order_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_purchase_order(db, org, member, order_id)


@router.get("/{org_id}/shipments", response_model=dict)
def list_shipments(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_shipments(db, org, member)


@router.post("/{org_id}/shipments", response_model=dict)
def create_shipment(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_shipment(db, org, member, body)


@router.patch("/{org_id}/shipments/{shipment_id}/status", response_model=dict)
def update_shipment_status(
    org_id: str, shipment_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_shipment_status(db, org, member, shipment_id, body.get("status", "in-transit"))


@router.delete("/{org_id}/shipments/{shipment_id}", response_model=dict)
def delete_shipment(org_id: str, shipment_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_shipment(db, org, member, shipment_id)


# --------------------------------------------------------------------------- #
# Finance
# --------------------------------------------------------------------------- #
@router.get("/{org_id}/ledger", response_model=dict)
def list_ledger(org_id: str, db: DbDep, member: MemberDep, category: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_ledger(db, org, member, category)


@router.post("/{org_id}/ledger", response_model=dict)
def create_ledger_entry(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_ledger_entry(db, org, member, body)


@router.delete("/{org_id}/ledger/{entry_id}", response_model=dict)
def delete_ledger_entry(org_id: str, entry_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_ledger_entry(db, org, member, entry_id)


@router.get("/{org_id}/invoices", response_model=dict)
def list_invoices(org_id: str, db: DbDep, member: MemberDep, status: str | None = None) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_invoices(db, org, member, status)


@router.post("/{org_id}/invoices", response_model=dict)
def create_invoice(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_invoice(db, org, member, body)


@router.patch("/{org_id}/invoices/{invoice_id}/status", response_model=dict)
def update_invoice_status(
    org_id: str, invoice_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep
) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_invoice_status(db, org, member, invoice_id, body.get("status", "draft"))


@router.delete("/{org_id}/invoices/{invoice_id}", response_model=dict)
def delete_invoice(org_id: str, invoice_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_invoice(db, org, member, invoice_id)


@router.get("/{org_id}/tax", response_model=dict)
def list_tax_items(org_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.list_tax_items(db, org, member)


@router.post("/{org_id}/tax", response_model=dict)
def create_tax_item(org_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.create_tax_item(db, org, member, body)


@router.patch("/{org_id}/tax/{item_id}", response_model=dict)
def update_tax_item(org_id: str, item_id: str, body: Annotated[dict, Body()], db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.update_tax_item(db, org, member, item_id, body)


@router.delete("/{org_id}/tax/{item_id}", response_model=dict)
def delete_tax_item(org_id: str, item_id: str, db: DbDep, member: MemberDep) -> dict:
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    db, member = _member(org, db, member)
    return org_ui.delete_tax_item(db, org, member, item_id)
