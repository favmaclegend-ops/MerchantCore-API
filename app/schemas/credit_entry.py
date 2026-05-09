from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreditEntryBase(BaseModel):
    customer_id: str
    customer_name: str
    customer_code: str | None = None
    balance: float = 0
    last_payment: str | None = None
    last_payment_amount: float | None = None
    status: str = "active"
    overdue_days: int | None = None


class CreditEntryCreate(CreditEntryBase):
    pass


class CreditEntryUpdate(BaseModel):
    balance: float | None = None
    last_payment: str | None = None
    last_payment_amount: float | None = None
    status: str | None = None
    overdue_days: int | None = None


class CreditEntryResponse(CreditEntryBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
