"""Per-organisation notification feed settings (one row per org)."""

from sqlalchemy import Boolean, Column, String

from app.db.session import Base
from app.models.base import BaseMixin, TimestampMixin


class OrgNotificationSetting(Base, BaseMixin, TimestampMixin):
    __tablename__ = "org_notification_settings"

    org_id = Column(String(36), index=True, nullable=False, unique=True)
    allow_admin_delete = Column(Boolean, default=False, nullable=False)
