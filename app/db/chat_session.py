from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

log = logging.getLogger(__name__)

chat_db_url = settings.sqlalchemy_chat_database_url
connect_args: dict = {}

if chat_db_url.startswith("mysql"):
    connect_args["connect_timeout"] = 10
    if "aiven" in chat_db_url.lower():
        connect_args["ssl"] = {}
        connect_args["read_timeout"] = 30


def _build_engine(url: str):
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=5,
        pool_recycle=1800,
        pool_timeout=30,
        connect_args=connect_args,
    )


try:
    chat_engine = _build_engine(chat_db_url)
    chat_engine.connect()
except Exception:
    sqlite_path = Path("./chat.db").resolve()
    sqlite_url = f"sqlite:///{sqlite_path}"
    log.warning("Cannot connect to %s — falling back to %s", chat_db_url, sqlite_url)
    chat_engine = _build_engine(sqlite_url)

ChatSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=chat_engine)

ChatBase = declarative_base()


def get_chat_db():
    db = ChatSessionLocal()
    try:
        yield db
    finally:
        db.close()
