from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    Base.metadata.create_all(bind=engine)


@app.on_event("shutdown")
async def shutdown() -> None:
    pass


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
