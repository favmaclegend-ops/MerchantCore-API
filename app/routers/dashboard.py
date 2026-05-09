from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.models.transaction import Transaction
from app.schemas.sale import DashboardStats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)) -> dict:
    total_revenue = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == "sale",
        Transaction.status == "completed",
    ).scalar()

    recent_txns = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == "sale",
        Transaction.status == "completed",
    ).scalar()

    total_orders = db.query(func.count(Transaction.id)).filter(
        Transaction.type == "sale",
    ).scalar()

    active_customers = db.query(func.count(Customer.id)).filter(
        Customer.status == "active",
    ).scalar()

    low_stock = db.query(func.count(Product.id)).filter(
        Product.status == "low-stock",
    ).scalar()

    inventory_value = db.query(
        func.coalesce(func.sum(Product.price * Product.stock), 0)
    ).scalar()

    return {
        "totalRevenue": float(total_revenue or 0),
        "monthlyRevenue": float(recent_txns or 0),
        "totalOrders": int(total_orders or 0),
        "activeCustomers": int(active_customers or 0),
        "lowStockAlerts": int(low_stock or 0),
        "inventoryValue": float(inventory_value or 0),
    }
