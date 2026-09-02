"""Organisation workspace + member accounts.

An organisation is created by a Super Admin whose email must be verified with a
six-digit code before anyone (including the Super Admin) can log in. Every member
belongs to exactly one organisation and carries a role that drives permissions.
"""


from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from app.db.session import Base
from app.models.base import BaseMixin, TimestampMixin


class Organisation(Base, BaseMixin, TimestampMixin):
    __tablename__ = "organisations"

    name = Column(String(255), unique=True, index=True, nullable=False)
    business_email = Column(String(255), unique=True, index=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_otp = Column(String(100), nullable=True)
    verification_otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, default=0, nullable=False)


class OrgMember(Base, BaseMixin, TimestampMixin):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_org_members_org_id_email"),
        UniqueConstraint("org_id", "username", name="uq_org_members_org_id_username"),
    )

    org_id = Column(String(36), index=True, nullable=False)
    user_id = Column(String(36), index=True, nullable=True)
    email = Column(String(255), index=True, nullable=False)
    username = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    role = Column(String(30), nullable=False, default="staff")
    job_title = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    data_blocked = Column(Boolean, default=False, nullable=False)
    disabled = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_otp = Column(String(100), nullable=True)
    verification_otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, default=0, nullable=False)

    @property
    def as_api(self) -> dict:
        """Member shape the frontend contract expects (no password, never)."""
        return {
            "id": self.id,
            "name": self.full_name,
            "email": self.email,
            "username": self.username,
            "phone": self.phone or "",
            "role": self.role,
            "jobTitle": self.job_title or "",
            "userId": self.user_id or "",
            "isActive": self.is_active,
            "dataBlocked": self.data_blocked,
            "disabled": self.disabled,
        }
