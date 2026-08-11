"""Organisation-scoped notification feed (the transparency log).

Every read is scoped by ``org_id`` and ``read_by`` tracks which member ids have
acknowledged each entry, so the same row is shared across the team while each
member sees their own unread count.
"""

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.org_notification import OrgNotification
from app.models.org_notification_settings import OrgNotificationSetting
from app.models.organisation import Organisation, OrgMember

PER_PAGE = 30


def _unread(member_id: str, read_by: str | None) -> bool:
    if not read_by:
        return True
    try:
        return member_id not in json.loads(read_by)
    except (TypeError, ValueError):
        return True


def _read_by(item: OrgNotification) -> list[str]:
    try:
        return json.loads(item.read_by or "[]")
    except (TypeError, ValueError):
        return []


def _as_api(item: OrgNotification, member_id: str) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "severity": item.severity,
        "is_alert": item.is_alert,
        "title": item.title,
        "message": item.message,
        "amount": item.amount,
        "ref": item.ref,
        "actor_name": item.actor_name,
        "actor_role": item.actor_role,
        "read_by": _read_by(item),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def create_notification(
    db: Session,
    *,
    org_id: str,
    kind: str,
    title: str,
    message: str,
    severity: str = "info",
    is_alert: bool = False,
    amount: float = 0,
    ref: str | None = None,
    actor_name: str | None = None,
    actor_role: str | None = None,
) -> OrgNotification:
    item = OrgNotification(
        org_id=org_id,
        kind=kind,
        title=title,
        message=message,
        severity=severity,
        is_alert=is_alert,
        amount=amount,
        ref=ref,
        actor_name=actor_name,
        actor_role=actor_role,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_notifications(
    db: Session, org: Organisation, member: OrgMember, kind: str | None = None, page: int = 1
) -> dict:
    query = db.query(OrgNotification).filter(OrgNotification.org_id == org.id)
    if kind:
        query = query.filter(OrgNotification.kind == kind)
    total = query.count()
    rows = query.order_by(OrgNotification.created_at.desc()).offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()
    return {
        "notifications": [_as_api(n, member.id) for n in rows],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // PER_PAGE)),
    }


def unread_count(db: Session, org: Organisation, member: OrgMember) -> int:
    rows = db.query(OrgNotification.read_by).filter(OrgNotification.org_id == org.id).all()
    return sum(1 for (read_by,) in rows if _unread(member.id, read_by))


def mark_read(db: Session, org: Organisation, member: OrgMember, notification_id: str) -> dict:
    item = (
        db.query(OrgNotification)
        .filter(OrgNotification.id == notification_id, OrgNotification.org_id == org.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    readers: set[str] = set()
    try:
        readers = set(json.loads(item.read_by or "[]"))
    except (TypeError, ValueError):
        readers = set()
    readers.add(member.id)
    item.read_by = json.dumps(sorted(readers))
    db.commit()
    db.refresh(item)
    return _as_api(item, member.id)


def mark_all_read(db: Session, org: Organisation, member: OrgMember) -> int:
    rows = db.query(OrgNotification).filter(OrgNotification.org_id == org.id).all()
    for item in rows:
        readers: set[str] = set()
        try:
            readers = set(json.loads(item.read_by or "[]"))
        except (TypeError, ValueError):
            readers = set()
        readers.add(member.id)
        item.read_by = json.dumps(sorted(readers))
    db.commit()
    return len(rows)


# --------------------------------------------------------------------------- #
# Deletion & feed settings
# --------------------------------------------------------------------------- #
def _can_delete(member: OrgMember, settings: OrgNotificationSetting | None) -> bool:
    if member.role == "super-admin":
        return True
    if member.role == "admin" and settings is not None and settings.allow_admin_delete:
        return True
    return False


def delete_notification(db: Session, org: Organisation, member: OrgMember, notification_id: str) -> None:
    settings = (
        db.query(OrgNotificationSetting).filter(OrgNotificationSetting.org_id == org.id).first()
    )
    if not _can_delete(member, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to delete notifications")
    item = (
        db.query(OrgNotification)
        .filter(OrgNotification.id == notification_id, OrgNotification.org_id == org.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    db.delete(item)
    db.commit()


def clear_all(db: Session, org: Organisation, member: OrgMember) -> int:
    settings = (
        db.query(OrgNotificationSetting).filter(OrgNotificationSetting.org_id == org.id).first()
    )
    if not _can_delete(member, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to delete notifications")
    count = (
        db.query(OrgNotification).filter(OrgNotification.org_id == org.id).delete(synchronize_session=False)
    )
    db.commit()
    return count


def get_settings(db: Session, org: Organisation, member: OrgMember) -> dict:
    setting = (
        db.query(OrgNotificationSetting).filter(OrgNotificationSetting.org_id == org.id).first()
    )
    if setting is None:
        setting = OrgNotificationSetting(org_id=org.id, allow_admin_delete=False)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return {"allow_admin_delete": setting.allow_admin_delete}


def update_settings(db: Session, org: Organisation, member: OrgMember, patch: dict) -> dict:
    if member.role != "super-admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the super admin can manage notification settings"
        )
    setting = (
        db.query(OrgNotificationSetting).filter(OrgNotificationSetting.org_id == org.id).first()
    )
    if setting is None:
        setting = OrgNotificationSetting(org_id=org.id, allow_admin_delete=False)
        db.add(setting)
    if "allow_admin_delete" in patch:
        setting.allow_admin_delete = bool(patch["allow_admin_delete"])
    db.commit()
    db.refresh(setting)
    return {"allow_admin_delete": setting.allow_admin_delete}
