from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import customer_cache, customer_list_cache
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate

router = APIRouter(tags=["customers"])


def _initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[-1][0]}".upper()
    return name[:2].upper() if name else ""


def _cache_key(user_id: str, suffix: str = "all") -> str:
    return f"user_{user_id}:{suffix}"


@router.get("/customers", response_model=list[CustomerResponse])
def list_customers(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list:
    cache_key = _cache_key(user.id)
    cached = customer_list_cache.get(cache_key)
    if cached is not None:
        return cached
    items = (
        db.query(Customer)
        .filter(Customer.user_id == user.id)
        .order_by(Customer.created_at.desc())
        .all()
    )
    for c in items:
        if not c.avatar:
            c.avatar = _initials(c.name)
    customer_list_cache[cache_key] = items
    return items


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Customer:
    cache_key = _cache_key(user.id, customer_id)
    cached = customer_cache.get(cache_key)
    if cached is not None:
        return cached
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == user.id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    if not customer.avatar:
        customer.avatar = _initials(customer.name)
    customer_cache[cache_key] = customer
    return customer


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    customer_in: CustomerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Customer:
    existing = db.query(Customer).filter(Customer.email == customer_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer with this email already exists")
    customer = Customer(user_id=user.id, **customer_in.model_dump())
    customer.avatar = _initials(customer.name)
    db.add(customer)
    db.commit()
    customer_cache[_cache_key(user.id, customer.id)] = customer
    customer_list_cache.pop(_cache_key(user.id), None)
    return customer


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: str,
    customer_in: CustomerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == user.id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    db.commit()
    customer_cache[_cache_key(user.id, customer.id)] = customer
    customer_list_cache.pop(_cache_key(user.id), None)
    return customer


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == user.id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()
    customer_cache.pop(_cache_key(user.id, customer_id), None)
    customer_list_cache.pop(_cache_key(user.id), None)
