from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    tier: str = "bronze"
    total_spent: float = 0
    credit_limit: float = 0
    last_purchase: str | None = None
    status: str = "active"


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    tier: str | None = None
    total_spent: float | None = None
    credit_limit: float | None = None
    last_purchase: str | None = None
    status: str | None = None


class CustomerResponse(CustomerBase):
    id: UUID
    avatar: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
