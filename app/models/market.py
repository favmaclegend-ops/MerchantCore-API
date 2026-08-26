"""Market models — stored in the separate ``merchant_market`` database.

These models use ``MarketBase`` (not the main ``Base``) so they live in an
isolated database that any client platform can consume via the public API.
"""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship

from app.db.market_session import MarketBase
from app.models.base import BaseMixin, TimestampMixin


class MarketShop(MarketBase, BaseMixin, TimestampMixin):
    __tablename__ = "market_shops"

    owner_id = Column(String(36), nullable=False, index=True)
    shop_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    profile_image = Column(String(1000), nullable=True)
    background_image = Column(String(1000), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    address = Column(String(500), nullable=True)
    city = Column(String(255), nullable=True)
    rating = Column(Float, nullable=False, default=0)
    verified = Column(Boolean, nullable=False, default=False)

    products = relationship("MarketProduct", back_populates="shop", cascade="all, delete-orphan")


class MarketProduct(MarketBase, BaseMixin, TimestampMixin):
    __tablename__ = "market_products"

    shop_id = Column(String(36), ForeignKey("market_shops.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    price = Column(Float, nullable=False, default=0)
    category = Column(String(100), nullable=False, default="General")
    description = Column(Text, nullable=True)
    in_stock = Column(Boolean, nullable=False, default=True)
    image_url = Column(String(1000), nullable=True)
    keywords = Column(Text, nullable=True)

    shop = relationship("MarketShop", back_populates="products")
    images = relationship("MarketProductImage", back_populates="product", cascade="all, delete-orphan")
    variants = relationship("MarketProductVariant", back_populates="product", cascade="all, delete-orphan")


class MarketProductImage(MarketBase, BaseMixin):
    __tablename__ = "market_product_images"

    product_id = Column(String(36), ForeignKey("market_products.id"), nullable=False, index=True)
    image_url = Column(String(1000), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    product = relationship("MarketProduct", back_populates="images")


class MarketProductVariant(MarketBase, BaseMixin):
    __tablename__ = "market_product_variants"

    product_id = Column(String(36), ForeignKey("market_products.id"), nullable=False, index=True)
    image = Column(String(1000), nullable=True)
    size = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    shape = Column(String(50), nullable=True)

    product = relationship("MarketProduct", back_populates="variants")


class MarketAdvert(MarketBase, BaseMixin, TimestampMixin):
    __tablename__ = "market_adverts"

    title = Column(String(255), nullable=True)
    advert_url = Column(String(1000), nullable=False)
    video_url = Column(String(1000), nullable=True)
    visit_link = Column(String(1000), nullable=True)
    active = Column(Boolean, nullable=False, default=True)


class MarketCategory(MarketBase, BaseMixin):
    __tablename__ = "market_categories"

    name = Column(String(100), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)
