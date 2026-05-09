from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


REGISTER_JSON = {
    "email": "test@example.com", "username": "testuser",
    "full_name": "Test User", "password": "password123",
}
REGISTER_JSON2 = {
    "email": "test2@example.com", "username": "testuser2",
    "full_name": "Test User 2", "password": "password123",
}
REGISTER_JSON3 = {
    "email": "ratelimit@example.com", "username": "ratelimit",
    "full_name": "Rate Limit", "password": "password123",
}
LOGIN_JSON = {"email": "test2@example.com", "password": "password123"}
LOGIN_JSON3 = {"email": "ratelimit@example.com", "password": "password123"}


def test_register(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        response = client.post("/api/v1/auth/register", json=REGISTER_JSON)
    assert response.status_code == 201, response.json()


def test_login_unverified(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        client.post("/api/v1/auth/register", json=REGISTER_JSON2)
    response = client.post("/api/v1/auth/login", json=LOGIN_JSON)
    assert response.status_code == 403, response.json()


def test_resend_rate_limit(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        client.post("/api/v1/auth/register", json=REGISTER_JSON3)
        response1 = client.post("/api/v1/auth/resend-verification", json=LOGIN_JSON3)
    assert response1.status_code == 200, response1.json()
    response2 = client.post("/api/v1/auth/resend-verification", json=LOGIN_JSON3)
    assert response2.status_code == 429, response2.json()
