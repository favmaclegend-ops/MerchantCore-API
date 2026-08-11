"""Organisation finance: ledger entries, invoices and tax items."""

from sqlalchemy import Column, Float, String, Text

from app.db.session import Base
from app.models.base import BaseMixin, OrgScopedMixin, TimestampMixin


class OrgLedgerEntry(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_ledger_entries"

    date = Column(String(20), nullable=True)  # YYYY-MM-DD
    account = Column(String(255), nullable=False)
    category = Column(String(20), nullable=False)  # income|expense|asset|liability
    description = Column(String(1000), nullable=True)
    amount = Column(Float, nullable=False, default=0)
    reference = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="posted")


class OrgInvoice(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_invoices"

    number = Column(String(50), nullable=False)
    customer = Column(String(255), nullable=False)
    issued_at = Column(String(20), nullable=True)  # YYYY-MM-DD
    due_at = Column(String(20), nullable=True)  # YYYY-MM-DD
    amount = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="draft")
    items = Column(Text, nullable=True)  # JSON array of {description, qty, unitPrice}


class OrgTaxItem(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_tax_items"

    name = Column(String(255), nullable=False)
    rate = Column(Float, nullable=False, default=0)
    basis = Column(Float, nullable=False, default=0)
    period = Column(String(20), nullable=True)
    due_at = Column(String(20), nullable=True)  # YYYY-MM-DD
    paid = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="upcoming")
