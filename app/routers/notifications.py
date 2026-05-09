from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import notification_list_cache
from app.db.session import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse, NotificationUpdate, UnreadCountResponse

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(db: Session = Depends(get_db)) -> list:
    cached = notification_list_cache.get("all")
    if cached is not None:
        return cached
    items = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()
    notification_list_cache["all"] = items
    return items


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
def unread_count(db: Session = Depends(get_db)) -> dict:
    count = db.query(Notification).filter(Notification.is_read == False).count()
    return {"count": count}


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(notification_id: str, db: Session = Depends(get_db)) -> Notification:
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    notification_list_cache.pop("all", None)
    return notification


@router.patch("/notifications/read-all")
def mark_all_as_read(db: Session = Depends(get_db)) -> dict:
    db.query(Notification).filter(Notification.is_read == False).update({"is_read": True})
    db.commit()
    notification_list_cache.pop("all", None)
    return {"message": "All notifications marked as read"}


@router.delete("/notifications/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(notification_id: str, db: Session = Depends(get_db)) -> None:
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    db.delete(notification)
    db.commit()
    notification_list_cache.pop("all", None)
