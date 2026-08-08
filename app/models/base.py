"""Shared column mixins used by every model so tables stay consistent.

- ``BaseMixin``      : UUID-style string primary key generated on insert.
- ``TimestampMixin`` : ``created_at`` / ``updated_at`` written in UTC.
- ``OrgScopedMixin`` : adds the ``org_id`` tenant column for multi-tenant rows.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, String


class BaseMixin:
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))


class TimestampMixin:
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class OrgScopedMixin:
    org_id = Column(String(36), index=True, nullable=False)
