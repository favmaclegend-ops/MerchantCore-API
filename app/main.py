from urllib.parse import urlparse

import pymysql
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.config import settings
from app.core.security import get_current_user
from app.db.chat_session import ChatBase, chat_engine
from app.db.market_session import MarketBase, market_engine
from app.db.session import Base, engine
from app.models import (  # noqa: F401
    CreditEntry,
    Customer,
    MarketAdvert,
    MarketCategory,
    MarketOrder,
    MarketProduct,
    MarketProductImage,
    MarketProductVariant,
    MarketShop,
    Notification,
    Organisation,
    OrgAttendance,
    OrgBenefit,
    OrgCreditEntry,
    OrgCustomer,
    OrgEmployee,
    OrgInvoice,
    OrgLedgerEntry,
    OrgMember,
    OrgNotification,
    OrgNotificationSetting,
    OrgPayrollRun,
    OrgPosTransaction,
    OrgProduct,
    OrgPurchaseOrder,
    OrgReview,
    OrgShipment,
    OrgSupplier,
    OrgTaxItem,
    OrgTimeEntry,
    Product,
    Sale,
    Transaction,
    User,
)
from app.models.chat import ChatMessage, ChatThread, ChatUserKey  # noqa: F401
from app.routers import (
    auth,
    chat,
    credit,
    customers,
    dashboard,
    market,
    notifications,
    org,
    org_auth,
    pos,
    products,
    transactions,
    users,
)


def _ensure_market_source_id_column(engine) -> None:
    """Add the ``source_id`` column to existing market_products tables.

    ``create_all`` never alters existing tables, so old market databases
    (sqlite fallback and MySQL alike) are migrated here on startup. The
    column is what ties a market listing back to the POS/inventory item it
    came from, which powers duplicate-upload prevention and the "On market"
    flag in the inventory UI.
    """
    try:
        inspector = inspect(engine)
        if "market_products" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("market_products")}
        with engine.begin() as conn:
            if "source_id" not in columns:
                conn.execute(
                    text("ALTER TABLE market_products ADD COLUMN source_id VARCHAR(255) NULL")
                )
        index_names = {idx["name"] for idx in inspect(engine).get_indexes("market_products")}
        if "uq_market_product_source" not in index_names:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_market_product_source "
                        "ON market_products (shop_id, source_id)"
                    )
                )
    except Exception:
        pass


def _ensure_market_order_delivery_columns(engine) -> None:
    """Add delivery columns to existing ``market_orders`` tables.

    ``create_all`` never alters existing tables, so market databases that
    predate the delivery-address feature are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        if "market_orders" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("market_orders")}
        additions = {
            "delivery_name": "ADD COLUMN delivery_name VARCHAR(255) NULL",
            "delivery_phone": "ADD COLUMN delivery_phone VARCHAR(50) NULL",
            "delivery_address": "ADD COLUMN delivery_address VARCHAR(500) NULL",
        }
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE market_orders {ddl}"))
    except Exception:
        pass


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(org_auth.router, prefix="/api/v1")

    protected = APIRouter(dependencies=[Depends(get_current_user)])
    protected.include_router(users.router)
    protected.include_router(products.router)
    protected.include_router(customers.router)
    protected.include_router(transactions.router)
    protected.include_router(credit.router)
    protected.include_router(pos.router)
    protected.include_router(dashboard.router)
    protected.include_router(notifications.router)
    application.include_router(protected, prefix="/api/v1")

    application.include_router(org.router, prefix="/api/v1")

    application.include_router(market.router, prefix="/api/v1")

    application.include_router(chat.router, prefix="/api/v1")

    return application


app = create_application()


@app.on_event("startup")
async def startup() -> None:
    db_url = settings.DATABASE_URL
    if db_url.startswith("mysql"):
        parsed = urlparse(db_url)
        db_name = parsed.path.lstrip("/")
        try:
            conn = pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=parsed.username or "root",
                password=parsed.password or "",
                connect_timeout=5,
            )
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
            conn.commit()
            conn.close()
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)

    market_db_url = settings.MARKET_DATABASE_URL
    if market_db_url.startswith("mysql"):
        parsed = urlparse(market_db_url)
        market_db_name = parsed.path.lstrip("/")
        try:
            conn = pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=parsed.username or "root",
                password=parsed.password or "",
                connect_timeout=5,
            )
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{market_db_name}`")
            conn.commit()
            conn.close()
        except Exception:
            pass

    MarketBase.metadata.create_all(bind=market_engine)
    _ensure_market_source_id_column(market_engine)
    _ensure_market_order_delivery_columns(market_engine)

    # --- Chat database (encrypted conversations) -----------------------------
    chat_db_url = settings.CHAT_DATABASE_URL
    if chat_db_url.startswith("mysql"):
        parsed = urlparse(chat_db_url)
        chat_db_name = parsed.path.lstrip("/")
        try:
            conn = pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=parsed.username or "root",
                password=parsed.password or "",
                connect_timeout=5,
            )
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{chat_db_name}`")
            conn.commit()
            conn.close()
        except Exception:
            pass

    ChatBase.metadata.create_all(bind=chat_engine)

    # Purge any chat messages older than the 4-day TTL on startup.
    from app.db.chat_session import ChatSessionLocal
    from app.services import chat as chat_service

    with ChatSessionLocal() as session:
        chat_service.purge_expired(session)


@app.on_event("shutdown")
async def shutdown() -> None:
    pass


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Merchant Core API is running"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
