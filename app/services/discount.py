from sqlalchemy import Column, DateTime, Integer, String, Text
from app.db.chat_session import ChatBase

class discount(ChatBase):
    
    __tablename__ = "discount_table"

    id = Column(primary_key=True, autoincrement=True)
    shope_name = Column(String(120), unique=False, nullable=False)
    product_id = Column(String(120), unique=False, nullable=False)
    old_price = Column(String(120), unique=False, nullable=False)
    new_price = Column(String(120), unique=False, nullable=False)
    discount_link = Column(String(120), unique=True, nullable=False)
    
    
