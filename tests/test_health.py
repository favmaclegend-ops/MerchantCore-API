import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from app.db.session import Base, get_db
from app.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session) -> TestClient:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_register(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        response = client.post("/api/v1/auth/register", json={"email": "test@example.com", "password": "password123"})
    assert response.status_code == 201


def test_login_unverified(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        client.post("/api/v1/auth/register", json={"email": "test2@example.com", "password": "password123"})
    response = client.post("/api/v1/auth/login", json={"email": "test2@example.com", "password": "password123"})
    assert response.status_code == 403


def test_resend_rate_limit(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        client.post("/api/v1/auth/register", json={"email": "ratelimit@example.com", "password": "password123"})
        response1 = client.post("/api/v1/auth/resend-verification", json={"email": "ratelimit@example.com", "password": "password123"})
    assert response1.status_code == 200
    response2 = client.post("/api/v1/auth/resend-verification", json={"email": "ratelimit@example.com", "password": "password123"})
    assert response2.status_code == 429
