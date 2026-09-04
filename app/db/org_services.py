from sqlalchemy import Integer, String, Float, Enum, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
import enum
import uuid
from datetime import datetime
from pydantic import BaseModel
from app.db.session import Base


class PriceTypeEnum(enum.Enum):
    flat = "flat"
    hourly = "hourly"
    variable = "variable"


class OrgServiceModel(Base):
    __tablename__ = "org_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    pricing_type: Mapped[Enum] = mapped_column(Enum(PriceTypeEnum), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    service_img: Mapped[str] = mapped_column(String(150), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate: Mapped[float] = mapped_column(Float, default=0.00, nullable=True)
    completed_at: Mapped[str] = mapped_column(String(40), nullable=True)
    isCompleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ServiceCreateSchema(BaseModel):
    name: str
    category: str | None = None
    pricing_type: str
    price: float
    description: str
    service_img: str
    status: str
    rate: float
