from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.credit_entry import CreditEntry
from app.models.customer import Customer
from app.models.product import Product
from app.models.transaction import Transaction
from app.schemas.sale import DashboardStats, RevenuePoint, RevenueTrend

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)) -> dict:
    total_revenue = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == "sale",
        Transaction.status == "completed",
    ).scalar()

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    monthly_revenue = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == "sale",
        Transaction.status == "completed",
        Transaction.created_at >= thirty_days_ago,
    ).scalar()

    total_orders = db.query(func.count(Transaction.id)).filter(
        Transaction.type == "sale",
    ).scalar()

    completed_orders = db.query(func.count(Transaction.id)).filter(
        Transaction.type == "sale",
        Transaction.status == "completed",
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

    total_products = db.query(func.count(Product.id)).scalar()

    credit_outstanding = db.query(
        func.coalesce(func.sum(CreditEntry.balance), 0)
    ).scalar()

    avg_ticket = (float(total_revenue or 0) / completed_orders) if completed_orders else 0

    return {
        "totalRevenue": float(total_revenue or 0),
        "monthlyRevenue": float(monthly_revenue or 0),
        "totalOrders": int(total_orders or 0),
        "activeCustomers": int(active_customers or 0),
        "lowStockAlerts": int(low_stock or 0),
        "inventoryValue": float(inventory_value or 0),
        "creditOutstanding": float(credit_outstanding or 0),
        "avgTicket": round(avg_ticket, 2),
        "totalProducts": int(total_products or 0),
    }


@router.get("/dashboard/revenue-trend", response_model=RevenueTrend)
def get_revenue_trend(db: Session = Depends(get_db)) -> dict:
    six_months_ago = datetime.now(UTC) - timedelta(days=180)
    txns = db.query(Transaction).filter(
        Transaction.type == "sale",
        Transaction.status == "completed",
        Transaction.created_at >= six_months_ago,
    ).all()

    monthly: dict[str, float] = defaultdict(float)
    for txn in txns:
        key = txn.created_at.strftime("%b") if txn.created_at else "Unknown"
        monthly[key] += txn.amount

    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    now = datetime.now(UTC)
    points = []
    for i in range(5, -1, -1):
        m = (now.month - i - 1) % 12
        label = month_order[m]
        points.append(RevenuePoint(month=label, revenue=round(monthly.get(label, 0), 2)))

    points.reverse()
    return {"months": points}
