from sqlalchemy import String, Float, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
import uuid
from datetime import datetime
from pydantic import BaseModel
from app.db.session import Base


class ServiceOrderModel(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    org_id: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    service_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(100), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    pricing_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    completed_at: Mapped[str] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ServiceOrderCreateSchema(BaseModel):
    service_id: str
    service_name: str
    customer_id: str | None = None
    customer_name: str
    price: float
    pricing_type: str
    category: str | None = None
