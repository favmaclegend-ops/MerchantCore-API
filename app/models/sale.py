from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text

from app.db.session import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    items = Column(Text, nullable=True)
    total = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime, default=datetime.now)
