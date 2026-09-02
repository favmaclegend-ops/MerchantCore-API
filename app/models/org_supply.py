"""Organisation supply chain: suppliers, purchase orders and shipments."""

from sqlalchemy import Column, Float, String, Text, UniqueConstraint

from app.db.session import Base
from app.models.base import BaseMixin, OrgScopedMixin, TimestampMixin


class OrgSupplier(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_suppliers"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_org_suppliers_org_id_email"),
    )

    name = Column(String(255), nullable=False)
    contact_person = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    address = Column(String(500), nullable=True)
    categories = Column(Text, nullable=True)  # JSON array of category strings
    payment_terms = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="active")


class OrgPurchaseOrder(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_purchase_orders"

    po_number = Column(String(50), nullable=False)
    supplier_id = Column(String(36), nullable=False)
    supplier_name = Column(String(255), nullable=False)
    items = Column(Text, nullable=False)  # JSON array of {product_id, product_name, qty, unit_price}
    total = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="draft")
    ordered_at = Column(String(50), nullable=True)  # ISO datetime
    received_at = Column(String(50), nullable=True)  # ISO datetime or ''


class OrgShipment(Base, BaseMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "org_shipments"

    tracking_number = Column(String(50), nullable=False)
    po_id = Column(String(36), nullable=False)
    po_number = Column(String(50), nullable=False)
    supplier_name = Column(String(255), nullable=False)
    market_order_id = Column(String(36), index=True, nullable=True)  # fulfilled market order
    customer_name = Column(String(255), nullable=True)  # buyer of the market order
    carrier = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="in-transit")
    eta = Column(String(50), nullable=True)  # ISO datetime
    delivered_at = Column(String(50), nullable=True)  # ISO datetime or ''
