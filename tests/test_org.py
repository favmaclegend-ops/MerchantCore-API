"""End-to-end tests for the organisation layer.

Covers registration with email verification (hashed, expiring code), the login
gate before verification, and multi-tenant isolation so a token from one org can
never touch another org's data.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def org_flow(client: TestClient):
    """Helper that captures the emailed verification code for an org."""

    def _register(email: str = "org@example.com", name: str = "Acme Ltd", password: str = "password123") -> dict:
        captured: dict = {}

        def fake_send(to_email: str, code: str, org_name: str) -> bool:
            captured["code"] = code
            return True

        with patch("app.routers.org_auth._send_code_email", side_effect=fake_send):
            resp = client.post(
                "/api/v1/auth/org/register",
                json={
                    "name": name,
                    "business_email": email,
                    "username": email.split("@")[0],
                    "full_name": "Jane Doe",
                    "password": password,
                },
            )
        assert resp.status_code == 201, resp.json()
        return {**resp.json(), "code": captured.get("code")}

    return _register


def test_org_register_and_verify_then_login(client: TestClient, org_flow) -> None:
    data = org_flow()

    # Cannot log in before the org is verified.
    pre = client.post("/api/v1/auth/org/login", json={"email": "org@example.com", "password": "password123"})
    assert pre.status_code == 403, pre.json()
    assert "not been verified" in pre.json()["detail"]

    # Wrong code is rejected and counts toward the attempt limit.
    wrong = client.post("/api/v1/auth/org/verify-email", json={"email": "org@example.com", "otp": "000000"})
    assert wrong.status_code == 400, wrong.json()

    # Correct code verifies the org.
    ok = client.post("/api/v1/auth/org/verify-email", json={"email": "org@example.com", "otp": data["code"]})
    assert ok.status_code == 200, ok.json()

    # Now login issues a member token carrying org_id.
    login = client.post("/api/v1/auth/org/login", json={"email": "org@example.com", "password": "password123"})
    assert login.status_code == 200, login.json()
    body = login.json()
    assert body["access_token"]
    assert body["role"] == "super-admin"
    assert body["org_id"]
    assert body["org_name"] == "Acme Ltd"


def test_org_duplicate_email_conflict(client: TestClient, org_flow) -> None:
    org_flow(email="dup@example.com", name="One Ltd")
    resp = client.post(
        "/api/v1/auth/org/register",
        json={
            "name": "Two Ltd",
            "business_email": "dup@example.com",
            "username": "dup2",
            "full_name": "Someone",
            "password": "password123",
        },
    )
    assert resp.status_code == 409, resp.json()


def test_org_cross_tenant_isolation(client: TestClient, org_flow) -> None:
    a = org_flow(email="tenant-a@example.com", name="Tenant A")
    b = org_flow(email="tenant-b@example.com", name="Tenant B")

    for code in (a["code"], b["code"]):
        client.post(
            "/api/v1/auth/org/verify-email",
            json={"email": "tenant-a@example.com" if code == a["code"] else "tenant-b@example.com", "otp": code},
        )

    token_a = client.post(
        "/api/v1/auth/org/login", json={"email": "tenant-a@example.com", "password": "password123"}
    ).json()["access_token"]
    org_b_id = client.post(
        "/api/v1/auth/org/login", json={"email": "tenant-b@example.com", "password": "password123"}
    ).json()["org_id"]

    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Org A's token cannot read Org B's dashboard.
    blocked = client.get(f"/api/v1/organisations/{org_b_id}/dashboard", headers=headers_a)
    assert blocked.status_code == 403, blocked.json()

    # And cannot list Org B's members either.
    blocked_members = client.get(f"/api/v1/organisations/{org_b_id}/members", headers=headers_a)
    assert blocked_members.status_code == 403, blocked_members.json()


def test_org_product_crud_and_pos_decrements_stock(client: TestClient, org_flow) -> None:
    data = org_flow(email="shop@example.com", name="Shop Co")
    client.post("/api/v1/auth/org/verify-email", json={"email": "shop@example.com", "otp": data["code"]})
    login = client.post("/api/v1/auth/org/login", json={"email": "shop@example.com", "password": "password123"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    org_id = login["org_id"]

    created = client.post(
        f"/api/v1/organisations/{org_id}/products",
        headers=headers,
        json={"name": "Widget", "sku": "WGT-001", "price": 10.0, "stock": 25, "category": "Parts"},
    )
    assert created.status_code == 200, created.json()
    product = created.json()
    assert product["status"] == "in-stock"
    product_id = product["id"]

    # Duplicate SKU rejected.
    dup = client.post(
        f"/api/v1/organisations/{org_id}/products",
        headers=headers,
        json={"name": "Widget Copy", "sku": "WGT-001", "price": 5.0},
    )
    assert dup.status_code == 409, dup.json()

    # POS checkout decrements stock.
    sale = client.post(
        f"/api/v1/organisations/{org_id}/pos/checkout",
        headers=headers,
        json={"items": [{"productId": product_id, "quantity": 3}], "paymentMethod": "cash"},
    )
    assert sale.status_code == 200, sale.json()
    assert sale.json()["amount"] == 30.0

    after = client.get(f"/api/v1/organisations/{org_id}/products/{product_id}", headers=headers).json()
    assert after["stock"] == 22

    # Refund restores stock.
    refund = client.post(f"/api/v1/organisations/{org_id}/transactions/{sale.json()['id']}/refund", headers=headers)
    assert refund.status_code == 200, refund.json()
    restored = client.get(f"/api/v1/organisations/{org_id}/products/{product_id}", headers=headers).json()
    assert restored["stock"] == 25


def test_org_dashboard_is_empty_on_fresh_org(client: TestClient, org_flow) -> None:
    data = org_flow(email="fresh@example.com", name="Fresh Org")
    client.post("/api/v1/auth/org/verify-email", json={"email": "fresh@example.com", "otp": data["code"]})
    login = client.post("/api/v1/auth/org/login", json={"email": "fresh@example.com", "password": "password123"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    org_id = login["org_id"]

    dashboard = client.get(f"/api/v1/organisations/{org_id}/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.json()
    body = dashboard.json()
    assert body["stats"]["totalRevenue"] == 0.0
    assert body["stats"]["productsCount"] == 0
    assert len(body["revenueTrend"]) == 31
    assert body["stockLevels"] == []
