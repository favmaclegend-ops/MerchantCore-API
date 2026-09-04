"""Public organisation auth: registration, verification, login, resend.

These routes are intentionally token-free. Registration creates the organisation
and its Super Admin member, then emails a hashed, expiring verification code.
No member (including the creator) can log in until the organisation is verified.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from app.db.org_services import ServiceCreateSchema, OrgServiceModel
from app.db.service_orders import ServiceOrderModel, ServiceOrderCreateSchema
import uuid
from datetime import UTC, datetime
from app.core.security import (
    MAX_OTP_ATTEMPTS,
    generate_otp,
    get_otp_expiry,
    get_password_hash,
    hash_otp,
    otp_is_expired,
    otp_matches,
    get_current_member
)
from app.core.permissions import require_admin
from app.db.session import get_db
from app.models.organisation import Organisation, OrgMember
from app.services.email import EmailNotConfiguredError, send_email
from app.services.org_notification import create_notification
from app.services.org_ui import _post_ledger
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

@router.post("/org_services", response_model=dict)
def create_service(service_data: ServiceCreateSchema, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    require_admin(req_user)
    try:
        org_id = req_user.org_id
        
        new_service = OrgServiceModel(
            organization_id=org_id, 
            name=service_data.name, 
            category=service_data.category, 
            pricing_type=service_data.pricing_type,
            price=float(service_data.price),
            service_id=str(uuid.uuid4()),
            description=service_data.description,
            service_img=service_data.service_img,
            status=service_data.status,
            rate=float(service_data.rate),
        )
        
        db.add(new_service)
        db.commit()
        db.refresh(new_service)
        create_notification(
            db,
            org_id=req_user.org_id,
            kind="service",
            title="Service added to catalog",
            message=f"New service: {service_data.name} (category {service_data.category})",
            severity="info",
            amount=float(service_data.price),
            ref=new_service.service_id,
            actor_name=req_user.full_name,
            actor_role=req_user.role,
        )
        return {"message": "Service created successfully", "service_id": new_service.id}
    except Exception as e:
        print("[server]An error occur while saving the new service:", e)
        return {"message": "Failed to create service", "error": str(e)}
    
@router.get("/get_org_services")
def get_org_service(req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    org_id = req_user.org_id
    services = db.query(OrgServiceModel).filter(OrgServiceModel.organization_id == org_id).all()
    return services

@router.patch("/org_services/{service_id}", response_model=dict)
def update_service(service_id: str, body: dict, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    require_admin(req_user)
    try:
        service = db.query(OrgServiceModel).filter(
            OrgServiceModel.service_id == service_id,
            OrgServiceModel.organization_id == req_user.org_id,
        ).first()
        if not service:
            return {"message": "Service not found"}

        if "status" in body:
            service.status = body["status"]
        if "isCompleted" in body:
            service.isCompleted = body["isCompleted"]
        if "completed_at" in body:
            service.completed_at = body["completed_at"]
        if "name" in body:
            service.name = body["name"]
        if "price" in body:
            service.price = float(body["price"])
        if "category" in body:
            service.category = body["category"]
        if "description" in body:
            service.description = body["description"]
        if "is_pinned" in body:
            service.is_pinned = bool(body["is_pinned"])

        db.commit()
        db.refresh(service)
        return {"message": "Service updated", "service_id": service.service_id}
    except Exception as e:
        print("[server] Error updating service:", e)
        return {"message": "Failed to update service", "error": str(e)}

@router.patch("/org_services/{service_id}/pin", response_model=dict)
def toggle_service_pin(service_id: str, body: dict, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    try:
        service = db.query(OrgServiceModel).filter(
            OrgServiceModel.service_id == service_id,
            OrgServiceModel.organization_id == req_user.org_id,
        ).first()
        if not service:
            return {"message": "Service not found"}

        if "is_pinned" in body:
            service.is_pinned = bool(body["is_pinned"])

        db.commit()
        db.refresh(service)
        return {"message": "Service updated", "service_id": service.service_id, "is_pinned": service.is_pinned}
    except Exception as e:
        print("[server] Error updating service pin:", e)
        return {"message": "Failed to update service", "error": str(e)}

@router.delete("/org_services/{service_id}", response_model=dict)
def delete_service(service_id: str, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    require_admin(req_user)
    try:
        service = db.query(OrgServiceModel).filter(
            OrgServiceModel.service_id == service_id,
            OrgServiceModel.organization_id == req_user.org_id,
        ).first()
        if not service:
            return {"message": "Service not found"}

        db.delete(service)
        db.commit()
        return {"message": "Service deleted", "service_id": service_id}
    except Exception as e:
        print("[server] Error deleting service:", e)
        return {"message": "Failed to delete service", "error": str(e)}


# ── Service Orders ──────────────────────────────────────────────────

@router.post("/service_orders", response_model=dict)
def create_service_order(order_data: ServiceOrderCreateSchema, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    try:
        new_order = ServiceOrderModel(
            org_id=req_user.org_id,
            order_id=str(uuid.uuid4()),
            service_id=order_data.service_id,
            service_name=order_data.service_name,
            customer_id=order_data.customer_id or "",
            customer_name=order_data.customer_name,
            price=float(order_data.price),
            pricing_type=order_data.pricing_type,
            category=order_data.category or "",
            status="active",
        )
        db.add(new_order)
        db.commit()
        db.refresh(new_order)
        create_notification(
            db,
            org_id=req_user.org_id,
            kind="service",
            title="New service order rendered",
            message=f"{order_data.service_name} rendered for {order_data.customer_name} at {order_data.price}",
            severity="info",
            amount=float(order_data.price),
            ref=new_order.order_id,
            actor_name=req_user.full_name,
            actor_role=req_user.role,
        )
        return {"message": "Service order created", "order_id": new_order.order_id}
    except Exception as e:
        print("[server] Error creating service order:", e)
        return {"message": "Failed to create service order", "error": str(e)}

@router.get("/service_orders")
def get_service_orders(req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    orders = db.query(ServiceOrderModel).filter(ServiceOrderModel.org_id == req_user.org_id).all()
    return orders

@router.patch("/service_orders/{order_id}", response_model=dict)
def update_service_order(order_id: str, body: dict, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    try:
        order = db.query(ServiceOrderModel).filter(
            ServiceOrderModel.order_id == order_id,
            ServiceOrderModel.org_id == req_user.org_id,
        ).first()
        if not order:
            return {"message": "Order not found"}

        was_completed = order.status == "completed"

        if "status" in body:
            order.status = body["status"]
        if "completed_at" in body:
            order.completed_at = body["completed_at"]

        if order.status == "completed" and not was_completed:
            order.completed_at = order.completed_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
            org = db.query(Organisation).filter(Organisation.id == req_user.org_id).first()
            _post_ledger(
                db,
                org,
                category="income",
                account="Service Sales",
                description=f"Service order completed: {order.service_name} for {order.customer_name}",
                amount=order.price,
                reference=order.order_id,
            )
            create_notification(
                db,
                org_id=req_user.org_id,
                kind="service",
                title="Service order completed",
                message=f"Order for {order.service_name} ({order.customer_name}) completed at {order.price}",
                severity="success",
                amount=order.price,
                ref=order.order_id,
                actor_name=req_user.full_name,
                actor_role=req_user.role,
            )

        db.commit()
        db.refresh(order)
        return {"message": "Order updated", "order_id": order.order_id}
    except Exception as e:
        print("[server] Error updating service order:", e)
        return {"message": "Failed to update order", "error": str(e)}

@router.delete("/service_orders/{order_id}", response_model=dict)
def delete_service_order(order_id: str, req_user: OrgMember = Depends(get_current_member), db: Session = Depends(get_db)):
    require_admin(req_user)
    try:
        order = db.query(ServiceOrderModel).filter(
            ServiceOrderModel.order_id == order_id,
            ServiceOrderModel.org_id == req_user.org_id,
        ).first()
        if not order:
            return {"message": "Order not found"}

        db.delete(order)
        db.commit()
        return {"message": "Order deleted", "order_id": order_id}
    except Exception as e:
        print("[server] Error deleting service order:", e)
        return {"message": "Failed to delete order", "error": str(e)}