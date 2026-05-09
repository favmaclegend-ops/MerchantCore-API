from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    link: str | None = None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationUpdate(BaseModel):
    is_read: bool = True


class UnreadCountResponse(BaseModel):
    count: int
