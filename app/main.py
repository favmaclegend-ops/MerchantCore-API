from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse

import pymysql
from app.config import settings
from app.db.session import Base, engine
from app.models import User  # noqa: F401
from app.routers import auth, users


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
    application.include_router(users.router, prefix="/api/v1")

    return application


app = create_application()


@app.on_event("startup")
async def startup() -> None:
    # Auto-create MySQL database if it doesn't exist
    db_url = settings.DATABASE_URL
    if db_url.startswith("mysql"):
        parsed = urlparse(db_url)
        db_name = parsed.path.lstrip("/")
        # Connect to MySQL server without specifying database
        conn = pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username or "root",
            password=parsed.password or "",
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
            conn.commit()
        finally:
            conn.close()

    # Run Alembic migrations
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@app.on_event("shutdown")
async def shutdown() -> None:
    pass


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Merchant Core API is running"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
