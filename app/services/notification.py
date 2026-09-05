from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import notification_list_cache
from app.models.notification import Notification


def _cache_key(user_id: str) -> str:
    return f"user_{user_id}"


def create_notification(
    db: Session,
    user_id: str,
    type: str,
    title: str,
    message: str,
    link: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
    )
    db.add(notification)
    db.commit()
    notification_list_cache.pop(_cache_key(user_id), None)
    return notification


def notify_new_sale(db: Session, user_id: str, amount: float, sale_id: str) -> Notification:
    return create_notification(
        db,
        user_id=user_id,
        type="new_sale",
        title="New Sale",
        message=f"A sale of ${amount:.2f} was completed.",
        link="/home/pos",
    )


def notify_low_stock(
    db: Session,
    user_id: str,
    product_name: str,
    product_id: str,
    stock: int,
) -> Notification:
    return create_notification(
        db,
        user_id=user_id,
        type="low_stock",
        title="Low Stock Alert",
        message=f"{product_name} is running low ({stock} remaining). Restock suggested.",
        link="/home/inventory",
    )


def notify_credit_payment(
    db: Session,
    user_id: str,
    customer_name: str,
    amount: float,
    entry_id: str,
) -> Notification:
    return create_notification(
        db,
        user_id=user_id,
        type="credit_payment",
        title="Payment Received",
        message=f"A payment of ${amount:.2f} was received from {customer_name}.",
        link="/home/credit",
    )


def list_notifications(db: Session, user_id: str, limit: int = 50) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def delete_notification(db: Session, user_id: str, notification_id: str) -> None:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    db.delete(notification)
    db.commit()
    notification_list_cache.pop(_cache_key(user_id), None)
