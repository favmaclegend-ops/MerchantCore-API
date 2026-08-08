"""Organisation transparency feed (notifications) with per-member read state."""

from sqlalchemy import Boolean, Column, Float, String, Text

from app.db.session import Base
from app.models.base import BaseMixin, OrgScopedMixin, TimestampMixin


class OrgNotification(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_notifications"

    kind = Column(String(30), nullable=False)
    severity = Column(String(20), nullable=False, default="info")
    is_alert = Column(Boolean, default=False, nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    amount = Column(Float, nullable=False, default=0)
    ref = Column(String(100), nullable=True)
    actor_name = Column(String(255), nullable=True)
    actor_role = Column(String(100), nullable=True)
    read_by = Column(Text, nullable=True)  # JSON array of member ids
