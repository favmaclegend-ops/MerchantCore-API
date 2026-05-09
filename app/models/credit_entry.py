from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.db.session import Base


class CreditEntry(Base):
    __tablename__ = "credit_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    customer_id = Column(String(36), nullable=False)
    customer_name = Column(String(255), nullable=False)
    customer_code = Column(String(50), nullable=True)
    balance = Column(Float, default=0)
    last_payment = Column(String(50), nullable=True)
    last_payment_amount = Column(Float, nullable=True)
    status = Column(String(20), default="active")
    overdue_days = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
