"""Market models — stored in the separate ``merchant_market`` database.

These models use ``MarketBase`` (not the main ``Base``) so they live in an
isolated database that any client platform can consume via the public API.
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.market_session import MarketBase
from app.models.base import BaseMixin, TimestampMixin


class MarketShop(MarketBase, BaseMixin, TimestampMixin):
    __tablename__ = "market_shops"

    owner_id = Column(String(50), nullable=False, index=True)
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
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "source_id",
            name="uq_market_product_source",
        ),
    )

    shop_id = Column(String(36), ForeignKey("market_shops.id"), nullable=False, index=True)
    source_id = Column(String(255), nullable=True, index=True)
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


class MarketService(MarketBase, BaseMixin, TimestampMixin):
    """A service listing uploaded by an organisation to the market.

    Stored in the market database, tied to the owning ``MarketShop`` via
    ``shop_id`` and to the underlying org service via ``source_id``. An image
    (``image_url``) is required before a service can be listed — enforced in
    the service layer. ``offer`` is optional promotional copy, ``rating``
    drives the star rating shown on the service card.
    """

    __tablename__ = "market_services"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "source_id",
            name="uq_market_service_source",
        ),
    )

    shop_id = Column(String(36), ForeignKey("market_shops.id"), nullable=False, index=True)
    source_id = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    price = Column(Float, nullable=False, default=0)
    offer = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=False)
    rating = Column(Float, nullable=False, default=0)
    _rating_count = Column(Integer, nullable=False, default=0)
    _rating_tallies = Column(Text, nullable=True)

    shop = relationship("MarketShop")


class MarketServiceRequest(MarketBase, BaseMixin, TimestampMixin):
    """A customer request for a service listed on the market.

    Created when a visitor clicks "Request for Service" on a service detail
    page.  The org can view and respond to requests via the org dashboard.
    ``status`` tracks the lifecycle: ``new`` → ``responded`` → ``completed``
    or ``cancelled``.
    """

    __tablename__ = "market_service_requests"

    service_id = Column(String(36), ForeignKey("market_services.id"), nullable=False, index=True)
    shop_id = Column(String(36), ForeignKey("market_shops.id"), nullable=False, index=True)
    org_id = Column(String(36), nullable=False, index=True)

    requester_name = Column(String(255), nullable=False)
    requester_phone = Column(String(50), nullable=False)
    note = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="new", index=True)
    response = Column(Text, nullable=True)
    responded_at = Column(DateTime, nullable=True)

    service = relationship("MarketService")
    shop = relationship("MarketShop")


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


class MarketOrder(MarketBase, BaseMixin, TimestampMixin):
    """A purchase placed against a single shop in the market.

    Stored in the market database (cross-platform commerce). The shop's
    ``owner_id`` (format ``org:<id>``) links the order back to an
    organisation, and ``buyer_id`` links it to the purchasing ``User`` in the
    main database. ``status`` drives the lifecycle: ``pending`` → ``completed``
    or ``cancelled``.
    """

    __tablename__ = "market_orders"

    buyer_id = Column(String(36), nullable=False, index=True)
    buyer_name = Column(String(255), nullable=False)
    buyer_email = Column(String(255), nullable=False)

    shop_id = Column(String(36), ForeignKey("market_shops.id"), nullable=False, index=True)
    org_id = Column(String(36), nullable=False, index=True)

    status = Column(String(20), nullable=False, default="pending", index=True)
    payment_method = Column(String(50), nullable=True)
    subtotal = Column(Float, nullable=False, default=0)
    tax = Column(Float, nullable=False, default=0)
    total = Column(Float, nullable=False, default=0)
    items = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    delivery_name = Column(String(255), nullable=True)
    delivery_phone = Column(String(50), nullable=True)
    delivery_address = Column(String(500), nullable=True)

    shop = relationship("MarketShop")
