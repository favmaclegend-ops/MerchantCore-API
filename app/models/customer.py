from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.db.session import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(50), nullable=True)
    company = Column(String(255), nullable=True)
    tier = Column(String(20), default="bronze")
    total_spent = Column(Float, default=0)
    credit_limit = Column(Float, default=0)
    last_purchase = Column(String(50), nullable=True)
    status = Column(String(20), default="active")
    avatar = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
