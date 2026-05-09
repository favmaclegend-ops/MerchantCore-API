from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, String

from app.db.session import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    type = Column(String(20), nullable=False)
    customer_name = Column(String(255), nullable=True)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="completed")
    items = Column(String(255), nullable=True)
    date = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
