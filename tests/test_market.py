"""Tests for the market service: source_id persistence + duplicate prevention."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.market_session import MarketBase
from app.models.market import MarketProduct
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