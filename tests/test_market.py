"""Tests for the market service: source_id persistence + duplicate prevention."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.market_session import MarketBase
from app.models.market import MarketProduct, MarketServiceRequest
from app.services import market


@pytest.fixture
def market_db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    MarketBase.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _shop(db, owner="org:o1", name="Shop A"):
    return market.create_shop(db, owner_id=owner, data={"shop_name": name})


def _product_data(name="Sugar 1kg", source_id="pos-1", price=15):
    return {
        "name": name,
        "price": price,
        "source_id": source_id,
        "category": "Groceries",
        "in_stock": True,
    }


def test_create_product_stores_source_id(market_db):
    shop = _shop(market_db)
    product = market.create_product(
        market_db, shop["id"], shop["owner_id"], data=_product_data()
    )
    assert product["source_id"] == "pos-1"
    row = (
        market_db.query(MarketProduct)
        .filter(MarketProduct.id == product["id"])
        .first()
    )
    assert row.source_id == "pos-1"


def test_shop_products_serialize_source_id(market_db):
    shop = _shop(market_db)
    market.create_product(
        market_db,
        shop["id"],
        shop["owner_id"],
        data=_product_data(name="Milk", source_id="pos-2", price=22),
    )
    data = market.get_shop(market_db, shop["id"])
    assert data["products"][0]["source_id"] == "pos-2"


def test_duplicate_source_id_is_rejected(market_db):
    shop = _shop(market_db)
    market.create_product(
        market_db, shop["id"], shop["owner_id"], data=_product_data()
    )
    with pytest.raises(HTTPException) as exc:
        market.create_product(
            market_db,
            shop["id"],
            shop["owner_id"],
            data=_product_data(name="Sugar 2"),
        )
    assert exc.value.status_code == 409


def test_same_source_id_allowed_across_shops(market_db):
    shop_a = _shop(market_db, owner="org:o1", name="Shop A")
    shop_b = _shop(market_db, owner="org:o2", name="Shop B")
    market.create_product(
        market_db, shop_a["id"], shop_a["owner_id"], data=_product_data()
    )
    created = market.create_product(
        market_db, shop_b["id"], shop_b["owner_id"], data=_product_data()
    )
    assert created["source_id"] == "pos-1"


def _service(db, shop, name="Cleaning", price=150):
    return market.create_service(
        db,
        shop["id"],
        shop["owner_id"],
        data={
            "name": name,
            "price": price,
            "image_url": "https://example.com/svc.png",
            "source_id": "svc-1",
        },
    )


def _request(db, service):
    return market.create_service_request(
        db,
        service_id=service["id"],
        requester_name="Bob",
        requester_phone="0700",
        user_id="u-1",
        note="Please",
    )


def test_completion_schedules_auto_delete(market_db):
    shop = _shop(market_db)
    service = _service(market_db, shop)
    req = _request(market_db, service)
    market.respond_to_service_request(
        market_db,
        request_id=req["id"],
        org_id="o1",
        response_text="On it",
        new_status="completed",
    )
    row = (
        market_db.query(MarketServiceRequest)
        .filter(MarketServiceRequest.id == req["id"])
        .first()
    )
    assert row.completed_at is not None
    assert row.delete_at is not None
    assert row.delete_at > row.completed_at


def test_delete_service_request_after_completed(market_db):
    shop = _shop(market_db)
    service = _service(market_db, shop)
    req = _request(market_db, service)
    market.respond_to_service_request(
        market_db,
        request_id=req["id"],
        org_id="o1",
        response_text="Done",
        new_status="completed",
    )
    deleted = market.delete_service_request(
        market_db, request_id=req["id"], org_id="o1"
    )
    assert deleted["id"] == req["id"]
    remaining = (
        market_db.query(MarketServiceRequest)
        .filter(MarketServiceRequest.id == req["id"])
        .first()
    )
    assert remaining is None


def test_cannot_delete_incomplete_request(market_db):
    shop = _shop(market_db)
    service = _service(market_db, shop)
    req = _request(market_db, service)
    with pytest.raises(HTTPException) as exc:
        market.delete_service_request(market_db, request_id=req["id"], org_id="o1")
    assert exc.value.status_code == 409


def test_purge_expired_service_requests(market_db):
    shop = _shop(market_db)
    service = _service(market_db, shop)
    req = _request(market_db, service)
    market.respond_to_service_request(
        market_db,
        request_id=req["id"],
        org_id="o1",
        response_text="Done",
        new_status="completed",
    )
    row = (
        market_db.query(MarketServiceRequest)
        .filter(MarketServiceRequest.id == req["id"])
        .first()
    )
    row.delete_at = row.delete_at.replace(year=2000)
    market_db.commit()
    removed = market.purge_expired_service_requests(market_db)
    assert removed == 1
    remaining = (
        market_db.query(MarketServiceRequest)
        .filter(MarketServiceRequest.id == req["id"])
        .first()
    )
    assert remaining is None