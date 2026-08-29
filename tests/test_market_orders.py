"""Tests for the market order workflow: create, complete via QR, cancel.

The order lives in the market database and completion writes a POS sale +
notifications into the app database (feeding the org dashboard).
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import decrypt_token, encrypt_token
from app.db.market_session import MarketBase
from app.db.session import Base
from app.services import market


@pytest.fixture
def market_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    MarketBase.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def app_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class _Member:
    org_id = "o1"
    full_name = "Ada Shopkeeper"
    role = "admin"
    id = "m1"


def _shop_with_product(mdb, product_id="prod-1"):
    shop = market.create_shop(mdb, owner_id="org:o1", data={"shop_name": "Shop A"})
    product = market.create_product(
        mdb,
        shop["id"],
        shop["owner_id"],
        data={
            "name": "Sugar 1kg",
            "price": 15,
            "source_id": product_id,
            "category": "Groceries",
            "in_stock": True,
        },
    )
    return shop, product


def _seed_org_product(app_db, product_id="prod-1", stock=10):
    from app.models.org_commerce import OrgProduct

    product = OrgProduct(
        org_id="o1",
        name="Sugar 1kg",
        sku="SKU-1",
        price=15,
        stock=stock,
        category="Groceries",
    )
    product.id = product_id
    app_db.add(product)
    app_db.commit()
    return app_db.query(OrgProduct).filter(OrgProduct.id == product_id).first()


def _create_order(mdb, shop_id):
    return market.create_order(
        mdb,
        shop_id=shop_id,
        buyer_id="u1",
        buyer_name="Alimatu Buyer",
        buyer_email="alimatu@example.com",
        items=[{"product_id": "p1", "source_id": "prod-1", "name": "Sugar 1kg", "price": 15, "quantity": 2}],
        payment_method="Cash",
        subtotal=30,
        tax=1.5,
        total=31.5,
        delivery_name="Alimatu Buyer",
        delivery_phone="+231 555 1234",
        delivery_address="24 Lynch St, Monrovia",
    )


def test_qr_token_round_trip(market_db):
    order = _create_order(market_db, _shop_with_product(market_db)[0]["id"])
    token = encrypt_token(order["id"])
    assert token != order["id"]
    assert decrypt_token(token) == order["id"]


def test_create_order_linked_to_org(market_db):
    shop, _ = _shop_with_product(market_db)
    order = _create_order(market_db, shop["id"])
    assert order["org_id"] == "o1"
    assert order["status"] == "pending"
    assert order["total"] == 31.5
    assert order["buyer_email"] == "alimatu@example.com"
    assert order["delivery_address"] == "24 Lynch St, Monrovia"
    assert order["delivery_phone"] == "+231 555 1234"
    assert order["delivery_name"] == "Alimatu Buyer"


def test_list_buyer_and_org_orders(market_db):
    shop, _ = _shop_with_product(market_db)
    _create_order(market_db, shop["id"])
    buyer = market.list_buyer_orders(market_db, buyer_id="u1")
    assert buyer["total"] == 1
    by_org = market.list_org_orders(market_db, org_id="o1")
    assert by_org["total"] == 1
    other = market.list_org_orders(market_db, org_id="other")
    assert other["total"] == 0


def test_complete_order_updates_stock_and_creates_transaction(market_db, app_db):
    shop, market_product = _shop_with_product(market_db, product_id="prod-1")
    org_product = _seed_org_product(app_db, "prod-1", stock=10)
    order = _create_order(market_db, shop["id"])

    from app.models.org_commerce import OrgPosTransaction
    from app.models.org_notification import OrgNotification

    result = market.complete_order(market_db, app_db, "o1", _Member(), order["id"])
    assert result["status"] == "completed"

    assert org_product.stock == 8

    txn = app_db.query(OrgPosTransaction).first()
    assert txn is not None
    assert txn.type == "sale"
    assert txn.amount == 31.5
    assert txn.status == "completed"

    org_notifications = app_db.query(OrgNotification).filter(OrgNotification.kind == "market_order").all()
    assert len(org_notifications) >= 1


def test_complete_order_wrong_org_forbidden(market_db, app_db):
    shop, _ = _shop_with_product(market_db, product_id="prod-1")
    order = _create_order(market_db, shop["id"])
    with pytest.raises(HTTPException) as exc:
        market.complete_order(market_db, app_db, "other-org", _Member(), order["id"])
    assert exc.value.status_code == 403


def test_complete_order_already_done_conflict(market_db, app_db):
    shop, _ = _shop_with_product(market_db, product_id="prod-1")
    order = _create_order(market_db, shop["id"])
    market.complete_order(market_db, app_db, "o1", _Member(), order["id"])
    with pytest.raises(HTTPException) as exc:
        market.complete_order(market_db, app_db, "o1", _Member(), order["id"])
    assert exc.value.status_code == 400


def test_cancel_order(market_db, app_db):
    shop, _ = _shop_with_product(market_db, product_id="prod-1")
    order = _create_order(market_db, shop["id"])
    result = market.cancel_order(market_db, app_db, "o1", _Member(), order["id"])
    assert result["status"] == "cancelled"

    from app.models.org_commerce import OrgPosTransaction

    assert app_db.query(OrgPosTransaction).count() == 0


def test_delete_order_removes_row(market_db):
    shop, _ = _shop_with_product(market_db, product_id="prod-1")
    order = _create_order(market_db, shop["id"])

    result = market.delete_order(market_db, order["id"])
    assert result["order_id"] == order["id"]

    assert market.list_org_orders(market_db, org_id="o1")["total"] == 0
    assert market.list_buyer_orders(market_db, buyer_id="u1")["total"] == 0


def test_delete_missing_order_raises(market_db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        market.delete_order(market_db, "does-not-exist")
    assert exc.value.status_code == 404
