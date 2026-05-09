from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SaleItem(BaseModel):
    id: str
    name: str
    price: float
    quantity: int


class SaleCreate(BaseModel):
    items: list[SaleItem]
    total: float
    payment_method: str


class SaleResponse(BaseModel):
    id: UUID
    items: str | None = None
    total: float
    payment_method: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    totalRevenue: float
    monthlyRevenue: float
    totalOrders: int
    activeCustomers: int
    lowStockAlerts: int
    inventoryValue: float
