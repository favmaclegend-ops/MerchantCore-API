from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
db_url = settings.sqlalchemy_database_url
if "aiven" in db_url.lower():
    # Aiven requires SSL but doesn't need explicit CA cert for PyMySQL
    connect_args["ssl"] = {}

engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
