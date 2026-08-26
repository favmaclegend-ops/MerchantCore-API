from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

log = logging.getLogger(__name__)

market_db_url = settings.sqlalchemy_market_database_url
connect_args: dict = {}

url_obj = make_url(market_db_url)

if url_obj.drivername.startswith("mysql"):
    connect_args["connect_timeout"] = 10
    if "aiven" in market_db_url.lower():
        connect_args["ssl"] = {}
        connect_args["read_timeout"] = 30


def _build_engine(url: str) -> tuple:
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=5,
        pool_recycle=1800,
        pool_timeout=30,
        connect_args=connect_args,
    )
    return engine


try:
    market_engine = _build_engine(market_db_url)
    market_engine.connect()
except Exception:
    sqlite_path = Path("./market.db").resolve()
    sqlite_url = f"sqlite:///{sqlite_path}"
    log.warning(
        "Cannot connect to %s — falling back to %s", market_db_url, sqlite_url
    )
    market_engine = _build_engine(sqlite_url)

MarketSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=market_engine
)

MarketBase = declarative_base()


def get_market_db():
    db = MarketSessionLocal()
    try:
        yield db
    finally:
        db.close()
