"""Organisation-scoped commerce data: products, customers, credit and POS sales.

Every row carries ``org_id`` so one backend can safely serve many organisations.
Product ``status`` is derived from ``stock`` (threshold 20) on every read instead
of being trusted from a stored value.
"""

from sqlalchemy import Column, Float, Integer, String, Text, UniqueConstraint

from app.db.session import Base
from app.models.base import BaseMixin, OrgScopedMixin, TimestampMixin

LOW_STOCK_THRESHOLD = 20


def product_status(stock: int) -> str:
    if stock <= 0:
        return "out-of-stock"
    if stock < LOW_STOCK_THRESHOLD:
        return "low-stock"
    return "in-stock"


class OrgProduct(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_products"
    __table_args__ = (
        UniqueConstraint("org_id", "sku", name="uq_org_products_org_id_sku"),
    )

    name = Column(String(255), nullable=False)
    sku = Column(String(100), nullable=False)
    price = Column(Float, nullable=False, default=0)
    stock = Column(Integer, nullable=False, default=0)
    category = Column(String(100), nullable=False, default="General")
    status = Column(String(20), nullable=False, default="in-stock")
    image = Column(String(1000), nullable=True)
    rating = Column(Float, nullable=True)


class OrgCustomer(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_customers"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_org_customers_org_id_email"),
    )

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    company = Column(String(255), nullable=True)
    total_spent = Column(Float, nullable=False, default=0)
    credit_limit = Column(Float, nullable=False, default=0)
    tier = Column(String(20), nullable=False, default="bronze")
    last_purchase = Column(String(50), nullable=True)


class OrgCreditEntry(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_credit_entries"

    customer_id = Column(String(36), nullable=False)
    customer_name = Column(String(255), nullable=False)
    customer_code = Column(String(50), nullable=True)
    balance = Column(Float, nullable=False, default=0)
    last_payment = Column(String(50), nullable=True)
    last_payment_amount = Column(Float, nullable=True, default=0)
    status = Column(String(20), nullable=False, default="active")
    overdue_days = Column(Integer, nullable=False, default=0)


class OrgPosTransaction(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_pos_transactions"

    type = Column(String(20), nullable=False, default="sale")
    customer_name = Column(String(255), nullable=True)
    amount = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="completed")
    items = Column(String(255), nullable=True)
    line_items = Column(Text, nullable=True)  # JSON array of sold items
    payment_method = Column(String(50), nullable=True)
