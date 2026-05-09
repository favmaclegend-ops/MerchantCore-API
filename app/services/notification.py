from sqlalchemy.orm import Session

from app.core.cache import notification_list_cache
from app.models.notification import Notification


def create_notification(
    db: Session,
    type: str,
    title: str,
    message: str,
    link: str | None = None,
) -> Notification:
    notification = Notification(
        type=type,
        title=title,
        message=message,
        link=link,
    )
    db.add(notification)
    db.commit()
    notification_list_cache.pop("all", None)
    return notification


def notify_new_sale(db: Session, amount: float, sale_id: str) -> Notification:
    return create_notification(
        db,
        type="new_sale",
        title="New Sale",
        message=f"A sale of ${amount:.2f} was completed.",
        link=f"/home/pos",
    )


def notify_low_stock(db: Session, product_name: str, product_id: str, stock: int) -> Notification:
    return create_notification(
        db,
        type="low_stock",
        title="Low Stock Alert",
        message=f"{product_name} is running low ({stock} remaining). Restock suggested.",
        link=f"/home/inventory",
    )


def notify_credit_payment(db: Session, customer_name: str, amount: float, entry_id: str) -> Notification:
    return create_notification(
        db,
        type="credit_payment",
        title="Payment Received",
        message=f"A payment of ${amount:.2f} was received from {customer_name}.",
        link=f"/home/credit",
    )
