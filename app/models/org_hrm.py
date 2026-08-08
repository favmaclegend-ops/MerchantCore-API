"""Organisation HRM: employees, benefits, payroll, time, attendance and reviews.

Entity attributes use camelCase at the API boundary (``jobTitle``, ``hireDate``),
relational fields stay snake_case (``employee_id``) — matching the frontend contract.
"""

from sqlalchemy import Column, Float, String, Text, UniqueConstraint

from app.db.session import Base
from app.models.base import BaseMixin, OrgScopedMixin, TimestampMixin

PAYROLL_TAX_RATE = 0.1
PAID_STATUSES = ("active", "probation", "on-leave")


class OrgEmployee(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_employees"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_org_employees_org_id_email"),
    )

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    department = Column(String(100), nullable=False)
    job_title = Column(String(100), nullable=True)
    employment_type = Column(String(20), nullable=False, default="full-time")
    hire_date = Column(String(20), nullable=True)  # YYYY-MM-DD
    salary = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="probation")
    benefits = Column(Text, nullable=True)  # JSON array of benefit ids

    @property
    def benefit_ids(self) -> list[str]:
        import json

        try:
            return json.loads(self.benefits or "[]")
        except (TypeError, ValueError):
            return []

    @property
    def as_api(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone or "",
            "department": self.department,
            "jobTitle": self.job_title or "",
            "employmentType": self.employment_type,
            "hireDate": self.hire_date or "",
            "salary": self.salary,
            "status": self.status,
            "benefits": self.benefit_ids,
        }


class OrgBenefit(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_benefits"

    name = Column(String(255), nullable=False)
    type = Column(String(30), nullable=False)
    cost = Column(Float, nullable=False, default=0)
    description = Column(String(1000), nullable=True)


class OrgPayrollRun(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_payroll_runs"

    period = Column(String(20), nullable=False)
    employee_id = Column(String(36), nullable=False)
    employee_name = Column(String(255), nullable=False)
    gross = Column(Float, nullable=False, default=0)
    tax = Column(Float, nullable=False, default=0)
    net = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    processed_at = Column(String(20), nullable=True)  # YYYY-MM-DD


class OrgTimeEntry(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_time_entries"

    employee_id = Column(String(36), nullable=False)
    employee_name = Column(String(255), nullable=False)
    date = Column(String(20), nullable=False)
    hours = Column(Float, nullable=False, default=0)
    overtime_hours = Column(Float, nullable=False, default=0)


class OrgAttendance(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_attendance"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "employee_id", "date", name="uq_org_attendance_org_emp_date"
        ),
    )

    employee_id = Column(String(36), nullable=False)
    employee_name = Column(String(255), nullable=False)
    date = Column(String(20), nullable=False)  # YYYY-MM-DD
    check_in = Column(String(10), nullable=True)  # HH:MM
    status = Column(String(20), nullable=False, default="present")


class OrgReview(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_reviews"

    employee_id = Column(String(36), nullable=False)
    employee_name = Column(String(255), nullable=False)
    period = Column(String(30), nullable=False)
    score = Column(Float, nullable=False, default=0)
    rating = Column(String(20), nullable=False, default="below")
    notes = Column(String(1000), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    reviewed_at = Column(String(20), nullable=True)  # YYYY-MM-DD


def review_rating(score: float) -> str:
    if score >= 4.5:
        return "exceeds"
    if score >= 3.5:
        return "meets"
    return "below"
