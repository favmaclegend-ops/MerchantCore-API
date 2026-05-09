from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import customer_cache, customer_list_cache
from app.db.session import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate

router = APIRouter(tags=["customers"])


def _initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[-1][0]}".upper()
    return name[:2].upper() if name else ""


@router.get("/customers", response_model=list[CustomerResponse])
def list_customers(db: Session = Depends(get_db)) -> list:
    cached = customer_list_cache.get("all")
    if cached is not None:
        return cached
    items = db.query(Customer).order_by(Customer.created_at.desc()).all()
    for c in items:
        if not c.avatar:
            c.avatar = _initials(c.name)
    customer_list_cache["all"] = items
    return items


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: str, db: Session = Depends(get_db)) -> Customer:
    cached = customer_cache.get(f"id:{customer_id}")
    if cached is not None:
        return cached
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if not customer.avatar:
        customer.avatar = _initials(customer.name)
    customer_cache[f"id:{customer_id}"] = customer
    return customer


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(customer_in: CustomerCreate, db: Session = Depends(get_db)) -> Customer:
    existing = db.query(Customer).filter(Customer.email == customer_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer with this email already exists")
    customer = Customer(**customer_in.model_dump())
    customer.avatar = _initials(customer.name)
    db.add(customer)
    db.commit()
    customer_cache[f"id:{customer.id}"] = customer
    customer_list_cache.pop("all", None)
    return customer


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: str, customer_in: CustomerUpdate, db: Session = Depends(get_db)) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    db.commit()
    customer_cache[f"id:{customer.id}"] = customer
    customer_list_cache.pop("all", None)
    return customer


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: str, db: Session = Depends(get_db)) -> None:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()
    customer_cache.pop(f"id:{customer_id}", None)
    customer_list_cache.pop("all", None)
