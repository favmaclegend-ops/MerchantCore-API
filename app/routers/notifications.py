from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import notification_list_cache
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse, UnreadCountResponse
from app.services.notification import (
    _cache_key,
    list_notifications,
)
from app.services.notification import (
    delete_notification as service_delete_notification,
)

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications_route(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list:
    cache_key = _cache_key(user.id)
    cached = notification_list_cache.get(cache_key)
    if cached is not None:
        return cached
    items = list_notifications(db, user.id)
    notification_list_cache[cache_key] = items
    return items


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
def unread_count_route(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, ~Notification.is_read)
        .count()
    )
    return {"count": count}


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    notification_list_cache.pop(_cache_key(user.id), None)
    return notification


@router.patch("/notifications/read-all")
def mark_all_as_read(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    db.query(Notification).filter(
        Notification.user_id == user.id, ~Notification.is_read
    ).update({"is_read": True})
    db.commit()
    notification_list_cache.pop(_cache_key(user.id), None)
    return {"message": "All notifications marked as read"}


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    service_delete_notification(db, user.id, notification_id)
    return {"message": "Notification deleted", "deleted": notification_id}
