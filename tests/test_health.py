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
REGISTER_JSON4 = {
    "email": "autosend@example.com",
    "username": "autosend",
    "full_name": "Autosend User",
    "password": "password123",
}
LOGIN_JSON = {"email": "test2@example.com", "password": "password123"}
LOGIN_JSON3 = {"email": "ratelimit@example.com", "password": "password123"}
LOGIN_JSON4 = {"email": "autosend@example.com", "password": "password123"}


def test_register(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        response = client.post("/api/v1/auth/register", json=REGISTER_JSON)
    assert response.status_code == 201, response.json()


def test_login_unverified(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        client.post("/api/v1/auth/register", json=REGISTER_JSON2)
        response = client.post("/api/v1/auth/login", json=LOGIN_JSON)
    assert response.status_code == 403, response.json()


def test_login_unverified_autosends_code(client: TestClient) -> None:
    sent: dict[str, str] = {}

    def fake_send(email: str, otp: str) -> bool:
        sent["email"] = email
        sent["otp"] = otp
        return True

    with patch("app.routers.auth.send_verification_email", side_effect=fake_send):
        client.post("/api/v1/auth/register", json=REGISTER_JSON4)
        response = client.post("/api/v1/auth/login", json=LOGIN_JSON4)
    assert response.status_code == 403, response.json()
    assert sent.get("email") == REGISTER_JSON4["email"]
    assert sent.get("otp")

    ok = client.post("/api/v1/auth/verify-email", json={"email": REGISTER_JSON4["email"], "otp": sent["otp"]})
    assert ok.status_code == 200, ok.json()

    login = client.post("/api/v1/auth/login", json=LOGIN_JSON4)
    assert login.status_code == 200, login.json()
    assert login.json()["access_token"]


def test_resend_rate_limit(client: TestClient) -> None:
    with patch("app.routers.auth.send_verification_email", return_value=True):
        client.post("/api/v1/auth/register", json=REGISTER_JSON3)
        response1 = client.post("/api/v1/auth/resend-verification", json=LOGIN_JSON3)
    assert response1.status_code == 200, response1.json()
    response2 = client.post("/api/v1/auth/resend-verification", json=LOGIN_JSON3)
    assert response2.status_code == 429, response2.json()


def test_resend_escalates_then_blocks(client: TestClient) -> None:
    EMAIL = "escalate@example.com"
    register = {
        "email": EMAIL,
        "username": "escalate",
        "full_name": "Escalate",
        "password": "password123",
    }
    body = {"email": EMAIL}
    clock = {"t": 0.0}

    def fake_time() -> float:
        return clock["t"]

    with patch("app.services.rate_limiter.time.time", side_effect=fake_time), patch(
        "app.routers.auth.send_verification_email", return_value=True
    ):
        client.post("/api/v1/auth/register", json=register)

        expect_wait = [
            ("60", 61),   # 1st send -> wait ~60s
            ("120", 121), # 2nd send -> wait ~120s
            ("240", 241), # 3rd send -> wait ~240s
            ("480", 481), # 4th send -> wait ~480s
            ("960", 961), # 5th send -> wait ~960s (still under 1h cap)
        ]
        for backoff, advance in expect_wait:
            ok = client.post("/api/v1/auth/resend-verification", json=body)
            assert ok.status_code == 200, ok.json()
            blocked = client.post("/api/v1/auth/resend-verification", json=body)
            assert blocked.status_code == 429, blocked.json()
            assert f"wait {backoff}" in blocked.json()["detail"], blocked.json()["detail"]
            clock["t"] += advance

        # 6th send triggers the temporary block.
        ok = client.post("/api/v1/auth/resend-verification", json=body)
        assert ok.status_code == 200, ok.json()
        blocked = client.post("/api/v1/auth/resend-verification", json=body)
        assert blocked.status_code == 429, blocked.json()
        assert "temporarily blocked" in blocked.json()["detail"], blocked.json()["detail"]
