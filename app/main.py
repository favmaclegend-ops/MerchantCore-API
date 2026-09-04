import asyncio
import logging
from urllib.parse import urlparse

import pymysql
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

from app.config import settings
from app.core.security import get_current_user
from app.db.chat_session import ChatBase, chat_engine
from app.db.market_session import MarketBase, market_engine
from app.db.session import Base, SessionLocal, engine
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
from app.db.org_services import OrgServiceModel  # noqa: F401
from app.db.service_orders import ServiceOrderModel  # noqa: F401
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


def _ensure_market_service_rating_columns(engine) -> None:
    """Add rating-tally columns to existing ``market_services`` tables.

    ``create_all`` never alters existing tables, so markets that listed
    services before ratings existed are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        if "market_services" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("market_services")}
        additions = {
            "_rating_count": "ADD COLUMN _rating_count INTEGER NOT NULL DEFAULT 0",
            "_rating_tallies": "ADD COLUMN _rating_tallies TEXT NULL",
        }
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE market_services {ddl}"))
    except Exception:
        pass


def _ensure_market_service_request_columns(engine) -> None:
    """Add email/address/user link columns to existing ``market_service_requests``.

    ``create_all`` never alters existing tables, so requests created before the
    inbox feature are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        if "market_service_requests" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("market_service_requests")}
        additions = {
            "requester_email": "ADD COLUMN requester_email VARCHAR(255) NULL",
            "requester_address": "ADD COLUMN requester_address VARCHAR(500) NULL",
            "user_id": "ADD COLUMN user_id VARCHAR(36) NULL",
            "completed_at": "ADD COLUMN completed_at DATETIME NULL",
        }
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE market_service_requests {ddl}"))
    except Exception:
        pass


def _ensure_org_invoice_columns(engine) -> None:
    """Add customer linkage columns to existing ``org_invoices`` tables.

    ``create_all`` never alters existing tables, so invoices created before the
    customer-email feature are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        if "org_invoices" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("org_invoices")}
        additions = {
            "customer_id": "ADD COLUMN customer_id VARCHAR(64) NULL",
            "customer_email": "ADD COLUMN customer_email VARCHAR(255) NULL",
        }
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE org_invoices {ddl}"))
    except Exception:
        pass


def _ensure_org_attendance_columns(engine) -> None:
    """Add check-out + method columns to existing ``org_attendance`` tables.

    ``create_all`` never alters existing tables, so attendance records created
    before the QR account-scan feature are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        if "org_attendance" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("org_attendance")}
        additions = {
            "check_out": "ADD COLUMN check_out VARCHAR(10) NULL",
            "check_in_method": "ADD COLUMN check_in_method VARCHAR(20) NULL",
            "check_out_method": "ADD COLUMN check_out_method VARCHAR(20) NULL",
        }
        with engine.begin() as conn:
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE org_attendance {ddl}"))
    except Exception:
        pass


def _ensure_user_id_columns(engine) -> None:
    """Add a ``user_id`` link column to org members and employees.

    ``create_all`` never alters existing tables, so rows created before the
    "select from existing user" feature are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        for table in ("org_members", "org_employees"):
            if table not in inspector.get_table_names():
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if "user_id" not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(36) NULL"))
    except Exception:
        pass


def _ensure_notification_visibility_columns(engine) -> None:
    """Add recipient/audience columns to org_notifications.

    ``user_id`` marks a notification as personal (sent to a specific user),
    ``admin_only`` marks it as visible only to admins. Together these let
    payroll payments stay private instead of being broadcast org-wide.
    """
    try:
        inspector = inspect(engine)
        if "org_notifications" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("org_notifications")}
        with engine.begin() as conn:
            if "user_id" not in columns:
                conn.execute(text("ALTER TABLE org_notifications ADD COLUMN user_id VARCHAR(36) NULL"))
            if "admin_only" not in columns:
                conn.execute(text("ALTER TABLE org_notifications ADD COLUMN admin_only BOOLEAN NOT NULL DEFAULT 0"))
    except Exception:
        pass


def _ensure_shipment_market_columns(engine) -> None:
    """Add market-order linkage columns to org_shipments.

    Let a shipment fulfil a customer's market order (not just a supplier PO):
    ``market_order_id`` holds the market order it completes and ``customer_name``
    records the buyer.
    """
    try:
        inspector = inspect(engine)
        if "org_shipments" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("org_shipments")}
        with engine.begin() as conn:
            if "market_order_id" not in columns:
                conn.execute(text("ALTER TABLE org_shipments ADD COLUMN market_order_id VARCHAR(36) NULL"))
            if "customer_name" not in columns:
                conn.execute(text("ALTER TABLE org_shipments ADD COLUMN customer_name VARCHAR(255) NULL"))
    except Exception:
        pass


def _ensure_org_service_pinned_column(engine) -> None:
    """Add the ``is_pinned`` column to existing ``org_services`` tables.

    ``create_all`` never alters existing tables, so services created before the
    pin-to-dashboard feature are migrated here on startup.
    """
    try:
        inspector = inspect(engine)
        if "org_services" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("org_services")}
        if "is_pinned" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE org_services ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT 0"))
    except Exception:
        pass


def _backfill_pos_ledger() -> None:
    """One-time idempotent backfill: mirror completed POS sales into the ledger.

    New sales already post an income ledger entry on completion, but sales made
    before that feature existed have no matching ledger line. This walks every
    completed sale and inserts an income entry unless one already exists with
    the same ``TX-<id>`` reference, so revenue and expenses are reconciled in a
    single source (accurate P&L). Safe to run on every startup.
    """
    try:
        with SessionLocal() as session:
            sales = (
                session.query(OrgPosTransaction)
                .filter(OrgPosTransaction.type == "sale", OrgPosTransaction.status == "completed")
                .all()
            )
            if not sales:
                return
            existing_refs = {
                r[0]
                for r in session.query(OrgLedgerEntry.reference)
                .filter(OrgLedgerEntry.category == "income")
                .all()
                if r[0]
            }
            inserted = 0
            for txn in sales:
                ref = f"TX-{txn.id[:8]}"
                if ref in existing_refs:
                    continue
                session.add(
                    OrgLedgerEntry(
                        org_id=txn.org_id,
                        date=txn.created_at.strftime("%Y-%m-%d") if txn.created_at else None,
                        account="POS Sales",
                        category="income",
                        description=f"Sale {txn.id[:8]} (backfill)",
                        amount=round(float(txn.amount or 0), 2),
                        reference=ref,
                        status="posted",
                    )
                )
                inserted += 1
            if inserted:
                session.commit()
    except Exception:
        # Never block startup because of a bookkeeping backfill.
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


_inbox_cleanup_task: "asyncio.Task | None" = None

_INBOX_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60  # every 6 hours


async def _inbox_cleanup_loop() -> None:
    """Periodically delete inbox messages whose linked service request completed > 4 days ago."""
    from app.db.market_session import MarketSessionLocal
    from app.services.market import purge_expired_inbox

    while True:
        try:
            with MarketSessionLocal() as mdb:
                removed = purge_expired_inbox(mdb)
            if removed:
                logger.info("Inbox cleanup removed %s expired message(s)", removed)
        except Exception:
            logger.exception("Inbox cleanup task failed")
        await asyncio.sleep(_INBOX_CLEANUP_INTERVAL_SECONDS)


app = create_application()


@app.on_event("startup")
async def startup() -> None:
    global _inbox_cleanup_task
    # Email / verification-code delivery diagnostic — surfaces a misconfigured
    # provider so it is obvious from the logs instead of silently failing.
    from app.services.email import email_provider_configured

    if not email_provider_configured():
        logger.error(
            "EMAIL NOT CONFIGURED: verification codes will NOT be delivered. "
            "Set RESEND_API_KEY, or SMTP_USER + SMTP_PASSWORD (plus SMTP_HOST and "
            "SMTP_FROM_EMAIL) in the environment."
        )
    else:
        mode = "Resend" if settings.RESEND_API_KEY else "SMTP"
        logger.info("Email provider configured (%s) — verification emails enabled.", mode)

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
    _ensure_org_invoice_columns(engine)
    _ensure_org_attendance_columns(engine)
    _ensure_user_id_columns(engine)
    _ensure_notification_visibility_columns(engine)
    _ensure_shipment_market_columns(engine)
    _ensure_org_service_pinned_column(engine)
    _backfill_pos_ledger()

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
    _ensure_market_service_rating_columns(market_engine)
    _ensure_market_service_request_columns(market_engine)

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

    # Purge inbox messages whose linked service request completed > 4 days ago,
    # then keep the cleanup running in the background while the app is up.
    from app.db.market_session import MarketSessionLocal
    from app.services.market import purge_expired_inbox

    with MarketSessionLocal() as mdb:
        purge_expired_inbox(mdb)

    _inbox_cleanup_task = asyncio.create_task(_inbox_cleanup_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    global _inbox_cleanup_task
    if _inbox_cleanup_task:
        _inbox_cleanup_task.cancel()
    pass


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Merchant Core API is running"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
