"""Business logic for every organisation UI screen.

Everything is scoped to ``org_id`` first (a tenant can never see another tenant's
rows) and then to the member's role. The functions below mirror the frontend
contracts in ``src/data/*.ts`` so the backend can eventually replace the mock
layers 1:1.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import require_manager, require_staff
from app.models.org_commerce import (
    LOW_STOCK_THRESHOLD,
    OrgCreditEntry,
    OrgCustomer,
    OrgPosTransaction,
    OrgProduct,
    product_status,
)
from app.models.org_finance import OrgInvoice, OrgLedgerEntry, OrgTaxItem
from app.models.org_hrm import (
    PAYROLL_TAX_RATE,
    OrgAttendance,
    OrgBenefit,
    OrgEmployee,
    OrgPayrollRun,
    OrgReview,
    OrgTimeEntry,
    review_rating,
)
from app.models.org_notification import OrgNotification
from app.models.org_supply import OrgPurchaseOrder, OrgShipment, OrgSupplier
from app.models.organisation import Organisation, OrgMember
from app.services.org_notification import create_notification

now_iso = lambda: datetime.now(UTC).isoformat()  # noqa: E731


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #
def product_as_api(product: OrgProduct) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "price": product.price,
        "stock": product.stock,
        "category": product.category,
        "status": product_status(product.stock),
        "image": product.image,
        "rating": product.rating,
    }


def list_products(
    db: Session,
    org: Organisation,
    member: OrgMember,
    search: str | None = None,
    category: str | None = None,
    page: int = 1,
) -> dict:
    query = db.query(OrgProduct).filter(OrgProduct.org_id == org.id)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(OrgProduct.name.ilike(like) | OrgProduct.sku.ilike(like))
    if category and category != "all":
        query = query.filter(OrgProduct.category == category)
    total = query.count()
    rows = query.order_by(OrgProduct.created_at).offset((page - 1) * 50).limit(50).all()
    return {
        "products": [product_as_api(p) for p in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // 50)),
    }


def _unique_sku(db: Session, org: Organisation, sku: str, exclude_id: str | None = None) -> None:
    query = db.query(OrgProduct).filter(OrgProduct.org_id == org.id, OrgProduct.sku == sku)
    if exclude_id:
        query = query.filter(OrgProduct.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists")


def get_product(db: Session, org: Organisation, member: OrgMember, product_id: str) -> dict:
    product = db.query(OrgProduct).filter(OrgProduct.id == product_id, OrgProduct.org_id == org.id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product_as_api(product)


def create_product(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_staff(member)
    _unique_sku(db, org, data["sku"])
    product = OrgProduct(
        org_id=org.id,
        name=data["name"],
        sku=data["sku"],
        price=_float(data.get("price")),
        stock=_int(data.get("stock")),
        category=data.get("category") or "General",
        image=data.get("image"),
        rating=_float(data.get("rating"), None) if data.get("rating") is not None else None,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    create_notification(
        db,
        org_id=org.id,
        kind="inventory",
        title="Product added",
        message=f"{member.full_name} added {product.name} to inventory.",
        severity="success",
        actor_name=member.full_name,
        actor_role=member.role,
        ref=product.id,
    )
    return product_as_api(product)


def update_product(db: Session, org: Organisation, member: OrgMember, product_id: str, data: dict) -> dict:
    require_staff(member)
    product = db.query(OrgProduct).filter(OrgProduct.id == product_id, OrgProduct.org_id == org.id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if "sku" in data and data["sku"] != product.sku:
        _unique_sku(db, org, data["sku"], exclude_id=product.id)
        product.sku = data["sku"]
    if "name" in data:
        product.name = data["name"]
    if "price" in data:
        product.price = _float(data.get("price"))
    if "stock" in data:
        product.stock = _int(data.get("stock"))
    if "category" in data:
        product.category = data["category"]
    if "image" in data:
        product.image = data["image"]
    if "rating" in data:
        product.rating = _float(data.get("rating"), None) if data["rating"] is not None else None
    db.commit()
    db.refresh(product)
    return product_as_api(product)


def delete_product(db: Session, org: Organisation, member: OrgMember, product_id: str) -> dict:
    require_manager(member)
    product = db.query(OrgProduct).filter(OrgProduct.id == product_id, OrgProduct.org_id == org.id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"message": "Product deleted"}


def get_product_status_summary(db: Session, org: Organisation, member: OrgMember) -> dict:
    rows = db.query(OrgProduct.stock).filter(OrgProduct.org_id == org.id).all()
    in_stock = low_stock = out_of_stock = 0
    for (stock,) in rows:
        s = product_status(stock)
        in_stock += s == "in-stock"
        low_stock += s == "low-stock"
        out_of_stock += s == "out-of-stock"
    return {
        "inStock": in_stock,
        "lowStock": low_stock,
        "outOfStock": out_of_stock,
        "threshold": LOW_STOCK_THRESHOLD,
    }


def check_low_stock(db: Session, org: Organisation) -> None:
    rows = db.query(OrgProduct).filter(OrgProduct.org_id == org.id).all()
    for product in rows:
        if 0 < product.stock < LOW_STOCK_THRESHOLD:
            create_notification(
                db,
                org_id=org.id,
                kind="low_stock",
                title="Low stock alert",
                message=f"{product.name} has only {product.stock} left.",
                severity="warning",
                is_alert=True,
                ref=product.id,
            )


# --------------------------------------------------------------------------- #
# Customers & credit
# --------------------------------------------------------------------------- #
def customer_as_api(customer: OrgCustomer) -> dict:
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone or "",
        "company": customer.company or "",
        "totalSpent": customer.total_spent,
        "creditLimit": customer.credit_limit,
        "tier": customer.tier,
        "lastPurchase": customer.last_purchase or "",
    }


def list_customers(db: Session, org: Organisation, member: OrgMember, search: str | None = None, page: int = 1) -> dict:
    query = db.query(OrgCustomer).filter(OrgCustomer.org_id == org.id)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(OrgCustomer.name.ilike(like) | OrgCustomer.email.ilike(like))
    total = query.count()
    rows = query.order_by(OrgCustomer.created_at).offset((page - 1) * 50).limit(50).all()
    return {
        "customers": [customer_as_api(c) for c in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // 50)),
    }


def get_customer(db: Session, org: Organisation, member: OrgMember, customer_id: str) -> dict:
    customer = db.query(OrgCustomer).filter(OrgCustomer.id == customer_id, OrgCustomer.org_id == org.id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer_as_api(customer)


def create_customer(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_staff(member)
    customer = OrgCustomer(
        org_id=org.id,
        name=data["name"],
        email=data.get("email", ""),
        phone=data.get("phone"),
        company=data.get("company"),
        total_spent=_float(data.get("totalSpent")),
        credit_limit=_float(data.get("creditLimit")),
        tier=data.get("tier") or "bronze",
        last_purchase=data.get("lastPurchase"),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer_as_api(customer)


def update_customer(db: Session, org: Organisation, member: OrgMember, customer_id: str, data: dict) -> dict:
    require_staff(member)
    customer = db.query(OrgCustomer).filter(OrgCustomer.id == customer_id, OrgCustomer.org_id == org.id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    for field, attr in (
        ("name", "name"),
        ("email", "email"),
        ("phone", "phone"),
        ("company", "company"),
        ("tier", "tier"),
        ("lastPurchase", "last_purchase"),
    ):
        if field in data:
            setattr(customer, attr, data[field])
    if "totalSpent" in data:
        customer.total_spent = _float(data.get("totalSpent"))
    if "creditLimit" in data:
        customer.credit_limit = _float(data.get("creditLimit"))
    db.commit()
    db.refresh(customer)
    return customer_as_api(customer)


def delete_customer(db: Session, org: Organisation, member: OrgMember, customer_id: str) -> dict:
    require_manager(member)
    customer = db.query(OrgCustomer).filter(OrgCustomer.id == customer_id, OrgCustomer.org_id == org.id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()
    return {"message": "Customer deleted"}


def credit_entry_as_api(entry: OrgCreditEntry) -> dict:
    return {
        "id": entry.id,
        "customerId": entry.customer_id,
        "customerName": entry.customer_name,
        "customerCode": entry.customer_code or "",
        "balance": entry.balance,
        "lastPayment": entry.last_payment or "",
        "lastPaymentAmount": entry.last_payment_amount or 0,
        "status": entry.status,
        "overdueDays": entry.overdue_days,
    }


def list_credit_entries(db: Session, org: Organisation, member: OrgMember, search: str | None = None) -> list[dict]:
    query = db.query(OrgCreditEntry).filter(OrgCreditEntry.org_id == org.id)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(OrgCreditEntry.customer_name.ilike(like) | OrgCreditEntry.customer_code.ilike(like))
    return [credit_entry_as_api(e) for e in query.order_by(OrgCreditEntry.created_at.desc()).all()]


def credit_summary(db: Session, org: Organisation, member: OrgMember) -> dict:
    rows = db.query(OrgCreditEntry).filter(OrgCreditEntry.org_id == org.id).all()
    total = sum(_float(e.balance) for e in rows)
    active = sum(1 for e in rows if e.status == "active")
    overdue = sum(1 for e in rows if e.status == "overdue")
    critical = sum(1 for e in rows if e.status == "critical")
    return {"totalOutstanding": total, "active": active, "overdue": overdue, "critical": critical}


def _recompute_credit_status(db: Session, org: Organisation, customer_id: str) -> None:
    """A customer's ledger row reflects their current standing."""
    entries = (
        db.query(OrgCreditEntry)
        .filter(OrgCreditEntry.org_id == org.id, OrgCreditEntry.customer_id == customer_id)
        .all()
    )
    for entry in entries:
        if entry.balance <= 0:
            entry.status = "active"
            entry.overdue_days = 0
        elif entry.overdue_days >= 60:
            entry.status = "critical"
        elif entry.overdue_days >= 30:
            entry.status = "overdue"
        else:
            entry.status = "active"
    db.commit()


def record_credit_purchase(
    db: Session, org: Organisation, member: OrgMember, customer_id: str, amount: float, code: str | None = None
) -> dict:
    require_staff(member)
    customer = db.query(OrgCustomer).filter(OrgCustomer.id == customer_id, OrgCustomer.org_id == org.id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")

    entry = (
        db.query(OrgCreditEntry)
        .filter(OrgCreditEntry.org_id == org.id, OrgCreditEntry.customer_id == customer_id)
        .first()
    )
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if entry:
        entry.balance += amount
        entry.last_payment = today
        entry.last_payment_amount = _float(entry.last_payment_amount) + amount
    else:
        entry = OrgCreditEntry(
            org_id=org.id,
            customer_id=customer.id,
            customer_name=customer.name,
            customer_code=code or customer.id[:8].upper(),
            balance=amount,
            last_payment=today,
            last_payment_amount=amount,
            status="active",
            overdue_days=0,
        )
        db.add(entry)
    customer.total_spent = _float(customer.total_spent) + amount
    db.commit()
    db.refresh(entry)
    _recompute_credit_status(db, org, customer_id)
    create_notification(
        db,
        org_id=org.id,
        kind="credit",
        title="Credit extended",
        message=f"{customer.name} now owes {amount:,.2f}.",
        severity="warning" if amount >= 5000 else "info",
        is_alert=amount >= 5000,
        amount=amount,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=entry.id,
    )
    return credit_entry_as_api(entry)


def make_credit_payment(db: Session, org: Organisation, member: OrgMember, customer_id: str, amount: float) -> dict:
    require_staff(member)
    entry = (
        db.query(OrgCreditEntry)
        .filter(OrgCreditEntry.org_id == org.id, OrgCreditEntry.customer_id == customer_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No credit account for this customer")
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive")
    entry.balance = max(0.0, entry.balance - amount)
    entry.last_payment = datetime.now(UTC).strftime("%Y-%m-%d")
    entry.last_payment_amount = amount
    entry.overdue_days = 0
    db.commit()
    _recompute_credit_status(db, org, customer_id)
    create_notification(
        db,
        org_id=org.id,
        kind="credit",
        title="Credit payment",
        message=f"{entry.customer_name} paid {amount:,.2f}.",
        severity="success",
        amount=amount,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=entry.id,
    )
    return credit_entry_as_api(entry)


# --------------------------------------------------------------------------- #
# POS
# --------------------------------------------------------------------------- #
def transaction_as_api(txn: OrgPosTransaction) -> dict:
    return {
        "id": txn.id,
        "type": txn.type,
        "customerName": txn.customer_name or "",
        "amount": txn.amount,
        "status": txn.status,
        "items": txn.items or "",
        "lineItems": txn.line_items or "",
        "paymentMethod": txn.payment_method or "",
        "createdAt": txn.created_at.isoformat() if txn.created_at else None,
    }


def checkout(
    db: Session,
    org: Organisation,
    member: OrgMember,
    items: Sequence[dict],
    payment_method: str,
    customer_name: str | None = None,
) -> dict:
    """POS sale: atomically decrement stock and record the transaction."""
    require_staff(member)
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No items in sale")

    total = 0.0
    line_items: list[dict] = []
    for raw in items:
        product_id = raw.get("productId") or raw.get("product_id")
        quantity = _int(raw.get("quantity") or raw.get("qty"), 1)
        if not product_id or quantity <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item in sale")

        product = db.query(OrgProduct).filter(OrgProduct.id == product_id, OrgProduct.org_id == org.id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {product_id} not found")
        if product.stock < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not enough stock for {product.name} (available: {product.stock})",
            )
        product.stock -= quantity
        line_total = _float(product.price) * quantity
        total += line_total
        line_items.append(
            {
                "productId": product.id,
                "name": product.name,
                "sku": product.sku,
                "quantity": quantity,
                "unitPrice": product.price,
                "lineTotal": round(line_total, 2),
            }
        )

    txn = OrgPosTransaction(
        org_id=org.id,
        type="sale",
        customer_name=customer_name,
        amount=round(total, 2),
        status="completed",
        items=", ".join(f"{i['quantity']}x {i['name']}" for i in line_items),
        line_items=json.dumps(line_items),
        payment_method=payment_method,
    )
    db.add(txn)
    db.flush()

    if customer_name:
        customer = db.query(OrgCustomer).filter(OrgCustomer.org_id == org.id, OrgCustomer.name == customer_name).first()
        if customer:
            customer.total_spent = _float(customer.total_spent) + total
            customer.last_purchase = datetime.now(UTC).strftime("%Y-%m-%d")
            _recompute_credit_status(db, org, customer.id)

    db.commit()
    db.refresh(txn)
    create_notification(
        db,
        org_id=org.id,
        kind="sale",
        title="New sale completed",
        message=f"{member.full_name} completed a sale of {total:,.2f}.",
        severity="success",
        amount=total,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=txn.id,
    )
    check_low_stock(db, org)
    return transaction_as_api(txn)


def list_transactions(db: Session, org: Organisation, member: OrgMember, page: int = 1, per_page: int = 20) -> dict:
    query = db.query(OrgPosTransaction).filter(OrgPosTransaction.org_id == org.id)
    total = query.count()
    rows = query.order_by(OrgPosTransaction.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "transactions": [transaction_as_api(t) for t in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // per_page)),
    }


def refund_transaction(db: Session, org: Organisation, member: OrgMember, transaction_id: str) -> dict:
    require_manager(member)
    txn = (
        db.query(OrgPosTransaction)
        .filter(OrgPosTransaction.id == transaction_id, OrgPosTransaction.org_id == org.id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    if txn.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction is not refundable")
    try:
        line_items = json.loads(txn.line_items or "[]")
    except (TypeError, ValueError):
        line_items = []
    for raw in line_items:
        product = (
            db.query(OrgProduct).filter(OrgProduct.id == raw.get("productId"), OrgProduct.org_id == org.id).first()
        )
        if product:
            product.stock += _int(raw.get("quantity"))
    txn.status = "refunded"
    db.commit()
    db.refresh(txn)
    create_notification(
        db,
        org_id=org.id,
        kind="sale",
        title="Sale refunded",
        message=f"{member.full_name} refunded transaction {transaction_id[:8]}.",
        severity="warning",
        amount=txn.amount,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=txn.id,
    )
    return transaction_as_api(txn)


# --------------------------------------------------------------------------- #
# HRM
# --------------------------------------------------------------------------- #
def employee_as_api(employee: OrgEmployee) -> dict:
    return {
        "id": employee.id,
        "name": employee.name,
        "email": employee.email,
        "phone": employee.phone or "",
        "department": employee.department,
        "jobTitle": employee.job_title or "",
        "employmentType": employee.employment_type,
        "hireDate": employee.hire_date or "",
        "salary": employee.salary,
        "status": employee.status,
        "benefits": employee.benefit_ids,
    }


def list_employees(
    db: Session, org: Organisation, member: OrgMember, department: str | None = None, search: str | None = None
) -> dict:
    query = db.query(OrgEmployee).filter(OrgEmployee.org_id == org.id)
    if department and department != "all":
        query = query.filter(OrgEmployee.department == department)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(OrgEmployee.name.ilike(like) | OrgEmployee.email.ilike(like))
    rows = query.order_by(OrgEmployee.created_at).all()
    return {
        "employees": [employee_as_api(e) for e in rows],
        "total": len(rows),
        "departments": sorted({e.department for e in rows}),
    }


def get_employee(db: Session, org: Organisation, member: OrgMember, employee_id: str) -> dict:
    employee = db.query(OrgEmployee).filter(OrgEmployee.id == employee_id, OrgEmployee.org_id == org.id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee_as_api(employee)


def create_employee(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    employee = OrgEmployee(
        org_id=org.id,
        name=data["name"],
        email=data.get("email", ""),
        phone=data.get("phone"),
        department=data.get("department", "General"),
        job_title=data.get("jobTitle"),
        employment_type=data.get("employmentType") or "full-time",
        hire_date=data.get("hireDate"),
        salary=_float(data.get("salary")),
        status=data.get("status") or "probation",
        benefits=json.dumps(data.get("benefits") or []),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    create_notification(
        db,
        org_id=org.id,
        kind="check_in",
        title="Employee added",
        message=f"{member.full_name} added {employee.name} to the team.",
        severity="success",
        actor_name=member.full_name,
        actor_role=member.role,
        ref=employee.id,
    )
    return employee_as_api(employee)


def update_employee(db: Session, org: Organisation, member: OrgMember, employee_id: str, data: dict) -> dict:
    require_manager(member)
    employee = db.query(OrgEmployee).filter(OrgEmployee.id == employee_id, OrgEmployee.org_id == org.id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    for field, attr in (
        ("name", "name"),
        ("email", "email"),
        ("phone", "phone"),
        ("department", "department"),
        ("jobTitle", "job_title"),
        ("employmentType", "employment_type"),
        ("hireDate", "hire_date"),
        ("status", "status"),
    ):
        if field in data:
            setattr(employee, attr, data[field])
    if "salary" in data:
        employee.salary = _float(data.get("salary"))
    if "benefits" in data:
        employee.benefits = json.dumps(data.get("benefits") or [])
    db.commit()
    db.refresh(employee)
    return employee_as_api(employee)


def delete_employee(db: Session, org: Organisation, member: OrgMember, employee_id: str) -> dict:
    require_manager(member)
    employee = db.query(OrgEmployee).filter(OrgEmployee.id == employee_id, OrgEmployee.org_id == org.id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    db.delete(employee)
    db.commit()
    return {"message": "Employee deleted"}


# --------------------------------------------------------------------------- #
# Benefits
# --------------------------------------------------------------------------- #
def benefit_as_api(benefit: OrgBenefit) -> dict:
    return {
        "id": benefit.id,
        "name": benefit.name,
        "type": benefit.type,
        "cost": benefit.cost,
        "description": benefit.description or "",
    }


def list_benefits(db: Session, org: Organisation, member: OrgMember) -> list[dict]:
    rows = db.query(OrgBenefit).filter(OrgBenefit.org_id == org.id).order_by(OrgBenefit.created_at).all()
    return [benefit_as_api(b) for b in rows]


def create_benefit(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    benefit = OrgBenefit(
        org_id=org.id,
        name=data["name"],
        type=data.get("type") or "other",
        cost=_float(data.get("cost")),
        description=data.get("description"),
    )
    db.add(benefit)
    db.commit()
    db.refresh(benefit)
    return benefit_as_api(benefit)


def update_benefit(db: Session, org: Organisation, member: OrgMember, benefit_id: str, data: dict) -> dict:
    require_manager(member)
    benefit = db.query(OrgBenefit).filter(OrgBenefit.id == benefit_id, OrgBenefit.org_id == org.id).first()
    if not benefit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benefit not found")
    for field in ("name", "type", "description"):
        if field in data:
            setattr(benefit, field, data[field])
    if "cost" in data:
        benefit.cost = _float(data.get("cost"))
    db.commit()
    db.refresh(benefit)
    return benefit_as_api(benefit)


def delete_benefit(db: Session, org: Organisation, member: OrgMember, benefit_id: str) -> dict:
    require_manager(member)
    benefit = db.query(OrgBenefit).filter(OrgBenefit.id == benefit_id, OrgBenefit.org_id == org.id).first()
    if not benefit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benefit not found")
    db.delete(benefit)
    db.commit()
    return {"message": "Benefit deleted"}


# --------------------------------------------------------------------------- #
# Payroll
# --------------------------------------------------------------------------- #
def payroll_as_api(run: OrgPayrollRun) -> dict:
    return {
        "id": run.id,
        "period": run.period,
        "employeeId": run.employee_id,
        "employeeName": run.employee_name,
        "gross": run.gross,
        "tax": run.tax,
        "net": run.net,
        "status": run.status,
        "processedAt": run.processed_at or "",
    }


def generate_payroll(db: Session, org: Organisation, member: OrgMember, period: str) -> dict:
    """Compute net pay for every employee for the period (single tax rate for now)."""
    require_manager(member)
    employees = db.query(OrgEmployee).filter(OrgEmployee.org_id == org.id).all()
    created = []
    for employee in employees:
        gross = _float(employee.salary)
        tax = round(gross * PAYROLL_TAX_RATE, 2)
        net = round(gross - tax, 2)
        run = OrgPayrollRun(
            org_id=org.id,
            period=period,
            employee_id=employee.id,
            employee_name=employee.name,
            gross=gross,
            tax=tax,
            net=net,
            status="pending",
        )
        db.add(run)
        created.append(run)
    db.commit()
    for run in created:
        db.refresh(run)
    create_notification(
        db,
        org_id=org.id,
        kind="payroll",
        title="Payroll generated",
        message=f"Payroll for {period} has been generated for {len(created)} employees.",
        severity="info",
        actor_name=member.full_name,
        actor_role=member.role,
    )
    return {"runs": [payroll_as_api(r) for r in created], "count": len(created)}


def list_payroll(db: Session, org: Organisation, member: OrgMember, period: str | None = None) -> dict:
    query = db.query(OrgPayrollRun).filter(OrgPayrollRun.org_id == org.id)
    if period:
        query = query.filter(OrgPayrollRun.period == period)
    rows = query.order_by(OrgPayrollRun.period.desc(), OrgPayrollRun.created_at).all()
    return {
        "runs": [payroll_as_api(r) for r in rows],
        "total": len(rows),
        "periods": sorted({r.period for r in rows}, reverse=True),
    }


def mark_payroll_paid(db: Session, org: Organisation, member: OrgMember, run_id: str) -> dict:
    require_manager(member)
    run = db.query(OrgPayrollRun).filter(OrgPayrollRun.id == run_id, OrgPayrollRun.org_id == org.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    run.status = "paid"
    run.processed_at = datetime.now(UTC).strftime("%Y-%m-%d")
    db.commit()
    db.refresh(run)
    create_notification(
        db,
        org_id=org.id,
        kind="payroll",
        title="Payroll marked paid",
        message=f"{run.employee_name}'s payroll for {run.period} was marked paid.",
        severity="success",
        amount=run.net,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=run.id,
    )
    return payroll_as_api(run)


def delete_payroll(db: Session, org: Organisation, member: OrgMember, run_id: str) -> dict:
    require_manager(member)
    run = db.query(OrgPayrollRun).filter(OrgPayrollRun.id == run_id, OrgPayrollRun.org_id == org.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    db.delete(run)
    db.commit()
    return {"message": "Payroll run deleted"}


# --------------------------------------------------------------------------- #
# Time, attendance, reviews
# --------------------------------------------------------------------------- #
def time_entry_as_api(entry: OrgTimeEntry) -> dict:
    return {
        "id": entry.id,
        "employeeId": entry.employee_id,
        "employeeName": entry.employee_name,
        "date": entry.date,
        "hours": entry.hours,
        "overtimeHours": entry.overtime_hours,
    }


def list_time_entries(db: Session, org: Organisation, member: OrgMember, employee_id: str | None = None) -> dict:
    query = db.query(OrgTimeEntry).filter(OrgTimeEntry.org_id == org.id)
    if employee_id:
        query = query.filter(OrgTimeEntry.employee_id == employee_id)
    rows = query.order_by(OrgTimeEntry.date.desc()).all()
    return {
        "entries": [time_entry_as_api(e) for e in rows],
        "total": len(rows),
        "hours": round(sum(e.hours for e in rows), 2),
    }


def create_time_entry(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    entry = OrgTimeEntry(
        org_id=org.id,
        employee_id=data["employeeId"],
        employee_name=data.get("employeeName") or "",
        date=data.get("date") or datetime.now(UTC).strftime("%Y-%m-%d"),
        hours=_float(data.get("hours")),
        overtime_hours=_float(data.get("overtimeHours")),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return time_entry_as_api(entry)


def delete_time_entry(db: Session, org: Organisation, member: OrgMember, entry_id: str) -> dict:
    require_manager(member)
    entry = db.query(OrgTimeEntry).filter(OrgTimeEntry.id == entry_id, OrgTimeEntry.org_id == org.id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    db.delete(entry)
    db.commit()
    return {"message": "Time entry deleted"}


def attendance_as_api(record: OrgAttendance) -> dict:
    return {
        "id": record.id,
        "employeeId": record.employee_id,
        "employeeName": record.employee_name,
        "date": record.date,
        "checkIn": record.check_in or "",
        "status": record.status,
    }


def list_attendance(
    db: Session, org: Organisation, member: OrgMember, date: str | None = None, employee_id: str | None = None
) -> dict:
    query = db.query(OrgAttendance).filter(OrgAttendance.org_id == org.id)
    if date:
        query = query.filter(OrgAttendance.date == date)
    if employee_id:
        query = query.filter(OrgAttendance.employee_id == employee_id)
    rows = query.order_by(OrgAttendance.date.desc()).all()
    return {
        "records": [attendance_as_api(r) for r in rows],
        "total": len(rows),
        "dates": sorted({r.date for r in rows}, reverse=True)[:30],
    }


def check_in(
    db: Session, org: Organisation, member: OrgMember, employee_id: str | None, date: str | None = None
) -> dict:
    require_staff(member)
    employee = db.query(OrgEmployee).filter(OrgEmployee.id == employee_id, OrgEmployee.org_id == org.id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    today = date or datetime.now(UTC).strftime("%Y-%m-%d")
    existing = (
        db.query(OrgAttendance)
        .filter(OrgAttendance.org_id == org.id, OrgAttendance.employee_id == employee_id, OrgAttendance.date == today)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{employee.name} already checked in today")
    record = OrgAttendance(
        org_id=org.id,
        employee_id=employee.id,
        employee_name=employee.name,
        date=today,
        check_in=datetime.now(UTC).strftime("%H:%M"),
        status="present",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    create_notification(
        db,
        org_id=org.id,
        kind="check_in",
        title="Employee checked in",
        message=f"{employee.name} checked in at {record.check_in}.",
        severity="success",
        actor_name=member.full_name,
        actor_role=member.role,
        ref=record.id,
    )
    return attendance_as_api(record)


def review_as_api(review: OrgReview) -> dict:
    return {
        "id": review.id,
        "employeeId": review.employee_id,
        "employeeName": review.employee_name,
        "period": review.period,
        "score": review.score,
        "rating": review.rating,
        "notes": review.notes or "",
        "status": review.status,
        "reviewedAt": review.reviewed_at or "",
    }


def list_reviews(db: Session, org: Organisation, member: OrgMember, employee_id: str | None = None) -> dict:
    query = db.query(OrgReview).filter(OrgReview.org_id == org.id)
    if employee_id:
        query = query.filter(OrgReview.employee_id == employee_id)
    rows = query.order_by(OrgReview.period.desc()).all()
    return {"reviews": [review_as_api(r) for r in rows], "total": len(rows)}


def create_review(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    employee = (
        db.query(OrgEmployee).filter(OrgEmployee.id == data.get("employeeId"), OrgEmployee.org_id == org.id).first()
    )
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    score = _float(data.get("score"), 0)
    review = OrgReview(
        org_id=org.id,
        employee_id=employee.id,
        employee_name=employee.name,
        period=data.get("period") or datetime.now(UTC).strftime("%Y-%m"),
        score=score,
        rating=data.get("rating") or review_rating(score),
        notes=data.get("notes"),
        status="pending",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review_as_api(review)


def complete_review(db: Session, org: Organisation, member: OrgMember, review_id: str) -> dict:
    require_manager(member)
    review = db.query(OrgReview).filter(OrgReview.id == review_id, OrgReview.org_id == org.id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    review.status = "completed"
    review.reviewed_at = datetime.now(UTC).strftime("%Y-%m-%d")
    db.commit()
    db.refresh(review)
    return review_as_api(review)


def delete_review(db: Session, org: Organisation, member: OrgMember, review_id: str) -> dict:
    require_manager(member)
    review = db.query(OrgReview).filter(OrgReview.id == review_id, OrgReview.org_id == org.id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    db.delete(review)
    db.commit()
    return {"message": "Review deleted"}


# --------------------------------------------------------------------------- #
# Supply chain
# --------------------------------------------------------------------------- #
def supplier_as_api(supplier: OrgSupplier) -> dict:
    try:
        categories = json.loads(supplier.categories or "[]")
    except (TypeError, ValueError):
        categories = []
    return {
        "id": supplier.id,
        "name": supplier.name,
        "contactPerson": supplier.contact_person or "",
        "email": supplier.email,
        "phone": supplier.phone or "",
        "address": supplier.address or "",
        "categories": categories,
        "paymentTerms": supplier.payment_terms or "",
        "status": supplier.status,
    }


def list_suppliers(db: Session, org: Organisation, member: OrgMember, search: str | None = None) -> dict:
    query = db.query(OrgSupplier).filter(OrgSupplier.org_id == org.id)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(OrgSupplier.name.ilike(like) | OrgSupplier.email.ilike(like))
    rows = query.order_by(OrgSupplier.created_at).all()
    return {"suppliers": [supplier_as_api(s) for s in rows], "total": len(rows)}


def create_supplier(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    supplier = OrgSupplier(
        org_id=org.id,
        name=data["name"],
        contact_person=data.get("contactPerson"),
        email=data.get("email", ""),
        phone=data.get("phone"),
        address=data.get("address"),
        categories=json.dumps(data.get("categories") or []),
        payment_terms=data.get("paymentTerms"),
        status=data.get("status") or "active",
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier_as_api(supplier)


def update_supplier(db: Session, org: Organisation, member: OrgMember, supplier_id: str, data: dict) -> dict:
    require_manager(member)
    supplier = db.query(OrgSupplier).filter(OrgSupplier.id == supplier_id, OrgSupplier.org_id == org.id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    for field, attr in (
        ("name", "name"),
        ("contactPerson", "contact_person"),
        ("email", "email"),
        ("phone", "phone"),
        ("address", "address"),
        ("paymentTerms", "payment_terms"),
        ("status", "status"),
    ):
        if field in data:
            setattr(supplier, attr, data[field])
    if "categories" in data:
        supplier.categories = json.dumps(data["categories"] or [])
    db.commit()
    db.refresh(supplier)
    return supplier_as_api(supplier)


def delete_supplier(db: Session, org: Organisation, member: OrgMember, supplier_id: str) -> dict:
    require_manager(member)
    supplier = db.query(OrgSupplier).filter(OrgSupplier.id == supplier_id, OrgSupplier.org_id == org.id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    db.delete(supplier)
    db.commit()
    return {"message": "Supplier deleted"}


def purchase_order_as_api(order: OrgPurchaseOrder) -> dict:
    try:
        items = json.loads(order.items or "[]")
    except (TypeError, ValueError):
        items = []
    return {
        "id": order.id,
        "poNumber": order.po_number,
        "supplierId": order.supplier_id,
        "supplierName": order.supplier_name,
        "items": items,
        "total": order.total,
        "status": order.status,
        "orderedAt": order.ordered_at or "",
        "receivedAt": order.received_at or "",
    }


def create_purchase_order(
    db: Session, org: Organisation, member: OrgMember, supplier_id: str, items: Sequence[dict]
) -> dict:
    require_manager(member)
    supplier = db.query(OrgSupplier).filter(OrgSupplier.id == supplier_id, OrgSupplier.org_id == org.id).first()
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PO must have at least one item")

    normalized = []
    total = 0.0
    for raw in items:
        product_id = raw.get("productId") or raw.get("product_id")
        product = None
        if product_id:
            product = db.query(OrgProduct).filter(OrgProduct.id == product_id, OrgProduct.org_id == org.id).first()
        product_name = raw.get("productName") or (product.name if product else "Unknown")
        unit_price = _float(raw.get("unitPrice") or (product.price if product else 0))
        quantity = _int(raw.get("quantity") or raw.get("qty"))
        if quantity <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quantity")
        line_total = unit_price * quantity
        total += line_total
        normalized.append(
            {
                "productId": product.id if product else None,
                "productName": product_name,
                "quantity": quantity,
                "unitPrice": round(unit_price, 2),
                "lineTotal": round(line_total, 2),
            }
        )

    order = OrgPurchaseOrder(
        org_id=org.id,
        po_number=f"PO-{datetime.now(UTC).strftime('%Y%m%d')}-{org.id[:4].upper()}",
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        items=json.dumps(normalized),
        total=round(total, 2),
        status="sent",
        ordered_at=now_iso(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    create_notification(
        db,
        org_id=org.id,
        kind="inventory",
        title="Purchase order created",
        message=f"PO {order.po_number} ({order.total:,.2f}) was sent to {supplier.name}.",
        severity="info",
        amount=order.total,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=order.id,
    )
    return purchase_order_as_api(order)


def list_purchase_orders(db: Session, org: Organisation, member: OrgMember, status_filter: str | None = None) -> dict:
    query = db.query(OrgPurchaseOrder).filter(OrgPurchaseOrder.org_id == org.id)
    if status_filter and status_filter != "all":
        query = query.filter(OrgPurchaseOrder.status == status_filter)
    rows = query.order_by(OrgPurchaseOrder.created_at.desc()).all()
    return {"orders": [purchase_order_as_api(o) for o in rows], "total": len(rows)}


def receive_purchase_order(db: Session, org: Organisation, member: OrgMember, order_id: str) -> dict:
    require_manager(member)
    order = (
        db.query(OrgPurchaseOrder).filter(OrgPurchaseOrder.id == order_id, OrgPurchaseOrder.org_id == org.id).first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    if order.status == "received":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already received")
    try:
        items = json.loads(order.items or "[]")
    except (TypeError, ValueError):
        items = []
    for raw in items:
        product_id = raw.get("productId")
        quantity = _int(raw.get("quantity"))
        if product_id:
            product = db.query(OrgProduct).filter(OrgProduct.id == product_id, OrgProduct.org_id == org.id).first()
            if product:
                product.stock += quantity
    order.status = "received"
    order.received_at = now_iso()
    db.commit()
    db.refresh(order)
    create_notification(
        db,
        org_id=org.id,
        kind="inventory",
        title="Purchase order received",
        message=f"PO {order.po_number} was marked received and stock updated.",
        severity="success",
        amount=order.total,
        actor_name=member.full_name,
        actor_role=member.role,
        ref=order.id,
    )
    return purchase_order_as_api(order)


def delete_purchase_order(db: Session, org: Organisation, member: OrgMember, order_id: str) -> dict:
    require_manager(member)
    order = (
        db.query(OrgPurchaseOrder).filter(OrgPurchaseOrder.id == order_id, OrgPurchaseOrder.org_id == org.id).first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    db.delete(order)
    db.commit()
    return {"message": "Purchase order deleted"}


def shipment_as_api(shipment: OrgShipment) -> dict:
    return {
        "id": shipment.id,
        "trackingNumber": shipment.tracking_number,
        "poId": shipment.po_id,
        "poNumber": shipment.po_number,
        "supplierName": shipment.supplier_name,
        "carrier": shipment.carrier,
        "status": shipment.status,
        "eta": shipment.eta or "",
        "deliveredAt": shipment.delivered_at or "",
    }


def create_shipment(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    po = (
        db.query(OrgPurchaseOrder)
        .filter(OrgPurchaseOrder.id == data.get("poId"), OrgPurchaseOrder.org_id == org.id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    shipment = OrgShipment(
        org_id=org.id,
        tracking_number=data.get("trackingNumber")
        or f"TRK-{org.id[:4].upper()}-{datetime.now(UTC).strftime('%H%M%S')}",
        po_id=po.id,
        po_number=po.po_number,
        supplier_name=po.supplier_name,
        carrier=data.get("carrier") or "Unknown carrier",
        status=data.get("status") or "in-transit",
        eta=data.get("eta"),
    )
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    return shipment_as_api(shipment)


def list_shipments(db: Session, org: Organisation, member: OrgMember) -> dict:
    rows = db.query(OrgShipment).filter(OrgShipment.org_id == org.id).order_by(OrgShipment.created_at.desc()).all()
    return {"shipments": [shipment_as_api(s) for s in rows], "total": len(rows)}


def update_shipment_status(db: Session, org: Organisation, member: OrgMember, shipment_id: str, status: str) -> dict:
    require_manager(member)
    shipment = db.query(OrgShipment).filter(OrgShipment.id == shipment_id, OrgShipment.org_id == org.id).first()
    if not shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    shipment.status = status
    if status == "delivered":
        shipment.delivered_at = now_iso()
    db.commit()
    db.refresh(shipment)
    return shipment_as_api(shipment)


def delete_shipment(db: Session, org: Organisation, member: OrgMember, shipment_id: str) -> dict:
    require_manager(member)
    shipment = db.query(OrgShipment).filter(OrgShipment.id == shipment_id, OrgShipment.org_id == org.id).first()
    if not shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    db.delete(shipment)
    db.commit()
    return {"message": "Shipment deleted"}


# --------------------------------------------------------------------------- #
# Finance
# --------------------------------------------------------------------------- #
def ledger_as_api(entry: OrgLedgerEntry) -> dict:
    return {
        "id": entry.id,
        "date": entry.date or "",
        "account": entry.account,
        "category": entry.category,
        "description": entry.description or "",
        "amount": entry.amount,
        "reference": entry.reference or "",
        "status": entry.status,
    }


def list_ledger(db: Session, org: Organisation, member: OrgMember, category: str | None = None) -> dict:
    query = db.query(OrgLedgerEntry).filter(OrgLedgerEntry.org_id == org.id)
    if category and category != "all":
        query = query.filter(OrgLedgerEntry.category == category)
    rows = query.order_by(OrgLedgerEntry.date.desc(), OrgLedgerEntry.created_at.desc()).all()
    income = round(sum(e.amount for e in rows if e.category == "income"), 2)
    expenses = round(sum(e.amount for e in rows if e.category == "expense"), 2)
    return {
        "entries": [ledger_as_api(e) for e in rows],
        "total": len(rows),
        "income": income,
        "expenses": expenses,
        "net": round(income - expenses, 2),
    }


def create_ledger_entry(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    entry = OrgLedgerEntry(
        org_id=org.id,
        date=data.get("date") or datetime.now(UTC).strftime("%Y-%m-%d"),
        account=data.get("account") or "General",
        category=data.get("category") or "income",
        description=data.get("description"),
        amount=_float(data.get("amount")),
        reference=data.get("reference"),
        status=data.get("status") or "posted",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ledger_as_api(entry)


def delete_ledger_entry(db: Session, org: Organisation, member: OrgMember, entry_id: str) -> dict:
    require_manager(member)
    entry = db.query(OrgLedgerEntry).filter(OrgLedgerEntry.id == entry_id, OrgLedgerEntry.org_id == org.id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ledger entry not found")
    db.delete(entry)
    db.commit()
    return {"message": "Ledger entry deleted"}


def invoice_as_api(invoice: OrgInvoice) -> dict:
    try:
        items = json.loads(invoice.items or "[]")
    except (TypeError, ValueError):
        items = []
    return {
        "id": invoice.id,
        "number": invoice.number,
        "customer": invoice.customer,
        "issuedAt": invoice.issued_at or "",
        "dueAt": invoice.due_at or "",
        "amount": invoice.amount,
        "status": invoice.status,
        "items": items,
    }


def list_invoices(db: Session, org: Organisation, member: OrgMember, status_filter: str | None = None) -> dict:
    query = db.query(OrgInvoice).filter(OrgInvoice.org_id == org.id)
    if status_filter and status_filter != "all":
        query = query.filter(OrgInvoice.status == status_filter)
    rows = query.order_by(OrgInvoice.created_at.desc()).all()
    paid = round(sum(i.amount for i in rows if i.status == "paid"), 2)
    outstanding = round(sum(i.amount for i in rows if i.status in ("sent", "overdue")), 2)
    return {
        "invoices": [invoice_as_api(i) for i in rows],
        "total": len(rows),
        "paid": paid,
        "outstanding": outstanding,
    }


def create_invoice(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    invoice = OrgInvoice(
        org_id=org.id,
        number=data.get("number") or f"INV-{datetime.now(UTC).strftime('%Y%m%d')}-{org.id[:4].upper()}",
        customer=data.get("customer") or "",
        issued_at=data.get("issuedAt") or datetime.now(UTC).strftime("%Y-%m-%d"),
        due_at=data.get("dueAt"),
        amount=_float(data.get("amount")),
        status=data.get("status") or "draft",
        items=json.dumps(data.get("items") or []),
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice_as_api(invoice)


def update_invoice_status(db: Session, org: Organisation, member: OrgMember, invoice_id: str, status: str) -> dict:
    require_manager(member)
    invoice = db.query(OrgInvoice).filter(OrgInvoice.id == invoice_id, OrgInvoice.org_id == org.id).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    invoice.status = status
    db.commit()
    db.refresh(invoice)
    return invoice_as_api(invoice)


def delete_invoice(db: Session, org: Organisation, member: OrgMember, invoice_id: str) -> dict:
    require_manager(member)
    invoice = db.query(OrgInvoice).filter(OrgInvoice.id == invoice_id, OrgInvoice.org_id == org.id).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    db.delete(invoice)
    db.commit()
    return {"message": "Invoice deleted"}


def tax_as_api(item: OrgTaxItem) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "rate": item.rate,
        "basis": item.basis,
        "period": item.period or "",
        "dueAt": item.due_at or "",
        "paid": item.paid,
        "status": item.status,
    }


def list_tax_items(db: Session, org: Organisation, member: OrgMember) -> dict:
    rows = db.query(OrgTaxItem).filter(OrgTaxItem.org_id == org.id).order_by(OrgTaxItem.due_at).all()
    total_due = round(sum((t.basis * t.rate / 100) - t.paid for t in rows), 2)
    return {
        "items": [tax_as_api(t) for t in rows],
        "total": len(rows),
        "totalDue": total_due,
    }


def create_tax_item(db: Session, org: Organisation, member: OrgMember, data: dict) -> dict:
    require_manager(member)
    item = OrgTaxItem(
        org_id=org.id,
        name=data.get("name") or "Tax",
        rate=_float(data.get("rate")),
        basis=_float(data.get("basis")),
        period=data.get("period"),
        due_at=data.get("dueAt"),
        paid=_float(data.get("paid")),
        status=data.get("status") or "upcoming",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return tax_as_api(item)


def update_tax_item(db: Session, org: Organisation, member: OrgMember, item_id: str, data: dict) -> dict:
    require_manager(member)
    item = db.query(OrgTaxItem).filter(OrgTaxItem.id == item_id, OrgTaxItem.org_id == org.id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax item not found")
    for field, attr in (
        ("name", "name"),
        ("rate", "rate"),
        ("basis", "basis"),
        ("period", "period"),
        ("dueAt", "due_at"),
        ("paid", "paid"),
        ("status", "status"),
    ):
        if field in data:
            setattr(item, attr, _float(data[field]) if field in ("rate", "basis", "paid") else data[field])
    db.commit()
    db.refresh(item)
    return tax_as_api(item)


def delete_tax_item(db: Session, org: Organisation, member: OrgMember, item_id: str) -> dict:
    require_manager(member)
    item = db.query(OrgTaxItem).filter(OrgTaxItem.id == item_id, OrgTaxItem.org_id == org.id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tax item not found")
    db.delete(item)
    db.commit()
    return {"message": "Tax item deleted"}


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def org_dashboard(db: Session, org: Organisation, member: OrgMember) -> dict:
    products = db.query(OrgProduct).filter(OrgProduct.org_id == org.id).all()
    customers = db.query(OrgCustomer).filter(OrgCustomer.org_id == org.id).all()
    employees = db.query(OrgEmployee).filter(OrgEmployee.org_id == org.id).all()
    sales = (
        db.query(OrgPosTransaction).filter(OrgPosTransaction.org_id == org.id, OrgPosTransaction.type == "sale").all()
    )
    credit = db.query(OrgCreditEntry).filter(OrgCreditEntry.org_id == org.id).all()
    notifications = db.query(OrgNotification).filter(OrgNotification.org_id == org.id).count()

    revenue = round(sum(t.amount for t in sales if t.status == "completed"), 2)
    pending_payroll = (
        db.query(OrgPayrollRun).filter(OrgPayrollRun.org_id == org.id, OrgPayrollRun.status == "pending").count()
    )

    # Last 30 days revenue trend, bucketed by day.
    cutoff = datetime.now(UTC) - timedelta(days=30)
    recent = [t for t in sales if t.created_at and t.created_at >= cutoff and t.status == "completed"]
    buckets: dict[str, float] = {}
    for t in recent:
        day = t.created_at.date().isoformat()
        buckets[day] = buckets.get(day, 0.0) + t.amount
    days = [(cutoff + timedelta(days=i)).date().isoformat() for i in range(31)]
    revenue_trend = [{"date": day, "revenue": round(buckets.get(day, 0.0), 2)} for day in days]

    stock_levels = [
        {
            "name": p.name,
            "stock": p.stock,
            "threshold": LOW_STOCK_THRESHOLD,
            "status": product_status(p.stock),
        }
        for p in products
    ]

    return {
        "stats": {
            "totalRevenue": revenue,
            "totalSales": len(sales),
            "productsCount": len(products),
            "customersCount": len(customers),
            "employeesCount": len(employees),
            "pendingPayroll": pending_payroll,
            "creditOutstanding": round(sum(c.balance for c in credit), 2),
            "notifications": notifications,
        },
        "revenueTrend": revenue_trend,
        "stockLevels": stock_levels,
    }
