from unittest.mock import patch

from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


REGISTER_JSON = {
    "email": "test@example.com",
    "username": "testuser",
    "full_name": "Test User",
    "password": "password123",
}
REGISTER_JSON2 = {
    "email": "test2@example.com",
    "username": "testuser2",
    "full_name": "Test User 2",
    "password": "password123",
}
REGISTER_JSON3 = {
    "email": "ratelimit@example.com",
    "username": "ratelimit",
    "full_name": "Rate Limit",
    "password": "password123",
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
