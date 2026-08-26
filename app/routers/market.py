"""Market HTTP API — public browsing + authenticated shop management.

Public endpoints require no auth so any client platform can browse.
Authenticated endpoints require a valid org member JWT (owner-only checks
are done inside the service layer).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_member
from app.db.market_session import get_market_db
from app.models.organisation import OrgMember
from app.services import market

router = APIRouter(prefix="/market", tags=["market"])

MarketDb = Annotated[Session, Depends(get_market_db)]
MemberDep = Annotated[OrgMember, Depends(get_current_member)]


# ---------------------------------------------------------------------------
# Public endpoints (no auth)
# ---------------------------------------------------------------------------

@router.get("/shops")
def list_shops(
    db: MarketDb,
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    return market.list_shops(db, search=search, page=page, limit=limit)


@router.get("/shops/{shop_id}")
def get_shop(shop_id: str, db: MarketDb) -> dict:
    return market.get_shop(db, shop_id)


@router.get("/products")
def list_products(
    db: MarketDb,
    category: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(22, ge=1, le=100),
) -> dict:
    return market.list_products(db, category=category, search=search, page=page, limit=limit)


@router.get("/products/{product_id}")
def get_product(product_id: str, db: MarketDb) -> dict:
    return market.get_product(db, product_id)


@router.get("/advert")
def list_adverts(db: MarketDb) -> list[dict]:
    return market.list_adverts(db)


@router.get("/categories")
def list_categories(db: MarketDb) -> list[dict]:
    return market.list_categories(db)


@router.get("/top-rated")
def top_rated_shops(db: MarketDb, limit: int = Query(4, ge=1, le=10)) -> list[dict]:
    return market.top_rated_shops(db, limit=limit)


# ---------------------------------------------------------------------------
# Authenticated endpoints (shop owner actions)
# ---------------------------------------------------------------------------

@router.post("/shops")
def create_shop(body: Annotated[dict, Body()], db: MarketDb, member: MemberDep) -> dict:
    return market.create_shop(db, owner_id=member.id, data=body)


@router.patch("/shops/{shop_id}")
def update_shop(
    shop_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.update_shop(db, shop_id=shop_id, owner_id=member.id, data=body)


@router.post("/shops/{shop_id}/products")
def create_product(
    shop_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.create_product(db, shop_id=shop_id, owner_id=member.id, data=body)


@router.patch("/products/{product_id}")
def update_product(
    product_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.update_product(db, product_id=product_id, owner_id=member.id, data=body)


@router.delete("/products/{product_id}")
def delete_product(product_id: str, db: MarketDb, member: MemberDep) -> dict:
    market.delete_product(db, product_id=product_id, owner_id=member.id)
    return {"message": "Product deleted"}
