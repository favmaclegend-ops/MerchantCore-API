from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TransactionBase(BaseModel):
    type: str
    customer_name: str | None = None
    amount: float
    status: str = "completed"
    items: str | None = None
    date: str | None = None


class TransactionCreate(TransactionBase):
    pass


class TransactionResponse(TransactionBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
