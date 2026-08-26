"""Market service layer — all business logic for shops, products, ads, and categories.

All functions receive a SQLAlchemy ``Session`` bound to the market database.
"""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.market import (
    MarketAdvert,
    MarketCategory,
    MarketProduct,
    MarketProductImage,
    MarketProductVariant,
    MarketShop,
)


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _shop_api(shop: MarketShop) -> dict[str, Any]:
    return {
        "id": shop.id,
        "owner_id": shop.owner_id,
        "shop_name": shop.shop_name,
        "description": shop.description,
        "profile_image": shop.profile_image,
        "background_image": shop.background_image,
        "lat": shop.lat,
        "lng": shop.lng,
        "address": shop.address,
        "city": shop.city,
        "rating": shop.rating,
        "verified": shop.verified,
        "created_at": shop.created_at.isoformat() if shop.created_at else None,
    }


def _variant_api(v: MarketProductVariant) -> dict[str, Any]:
    return {
        "id": v.id,
        "image": v.image,
        "size": v.size,
        "color": v.color,
        "shape": v.shape,
    }


def _product_api(p: MarketProduct) -> dict[str, Any]:
    return {
        "id": p.id,
        "shop_id": p.shop_id,
        "name": p.name,
        "price": p.price,
        "category": p.category,
        "description": p.description,
        "in_stock": p.in_stock,
        "image_url": p.image_url,
        "keywords": p.keywords.split(",") if p.keywords else [],
        "images": [_product_image_api(img) for img in sorted(p.images, key=lambda i: i.sort_order)],
        "variants": [_variant_api(v) for v in p.variants],
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _product_image_api(img: MarketProductImage) -> dict[str, Any]:
    return {"id": img.id, "image_url": img.image_url, "sort_order": img.sort_order}


def _advert_api(a: MarketAdvert) -> dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "advert_url": a.advert_url,
        "video_url": a.video_url,
        "visit_link": a.visit_link,
        "active": a.active,
    }


def _category_api(c: MarketCategory) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "sort_order": c.sort_order}


# ---------------------------------------------------------------------------
# Public read helpers (no auth required)
# ---------------------------------------------------------------------------

def list_shops(db: Session, search: str | None = None, page: int = 1, limit: int = 20) -> dict[str, Any]:
    q = db.query(MarketShop)
    if search:
        term = f"%{search.strip().lower()}%"
        q = q.filter(
            MarketShop.shop_name.ilike(term) | MarketShop.city.ilike(term) | MarketShop.address.ilike(term)
        )
    total = q.count()
    shops = q.order_by(MarketShop.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {"shops": [_shop_api(s) for s in shops], "total": total, "page": page, "limit": limit}


def get_shop(db: Session, shop_id: str) -> dict[str, Any]:
    shop = db.query(MarketShop).filter(MarketShop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    products = db.query(MarketProduct).filter(MarketProduct.shop_id == shop_id).order_by(MarketProduct.created_at.desc()).all()
    data = _shop_api(shop)
    data["products"] = [_product_api(p) for p in products]
    return data


def list_products(
    db: Session,
    category: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 22,
) -> dict[str, Any]:
    q = db.query(MarketProduct)
    if category and category.lower() != "all":
        q = q.filter(MarketProduct.category == category)
    if search:
        term = f"%{search.strip().lower()}%"
        q = q.filter(
            MarketProduct.name.ilike(term)
            | MarketProduct.category.ilike(term)
            | MarketProduct.keywords.ilike(term)
        )
    total = q.count()
    products = q.order_by(MarketProduct.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {"products": [_product_api(p) for p in products], "total": total, "page": page, "limit": limit}


def get_product(db: Session, product_id: str) -> dict[str, Any]:
    product = db.query(MarketProduct).filter(MarketProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return _product_api(product)


def list_adverts(db: Session) -> list[dict[str, Any]]:
    ads = db.query(MarketAdvert).filter(MarketAdvert.active == True).order_by(MarketAdvert.created_at.desc()).all()  # noqa: E712
    return [_advert_api(a) for a in ads]


def list_categories(db: Session) -> list[dict[str, Any]]:
    cats = db.query(MarketCategory).order_by(MarketCategory.sort_order.asc()).all()
    if not cats:
        return [{"id": "default", "name": c, "sort_order": i} for i, c in enumerate(
            ["All", "Beverages", "Dairy", "Electronics", "Watch", "Car", "Perfume", "Wine"]
        )]
    return [_category_api(c) for c in cats]


def top_rated_shops(db: Session, limit: int = 4) -> list[dict[str, Any]]:
    shops = db.query(MarketShop).order_by(MarketShop.rating.desc()).limit(limit).all()
    return [_shop_api(s) for s in shops]


# ---------------------------------------------------------------------------
# Write helpers (auth required — shop owner only)
# ---------------------------------------------------------------------------

def create_shop(db: Session, owner_id: str, data: dict[str, Any]) -> dict[str, Any]:
    shop = MarketShop(
        owner_id=owner_id,
        shop_name=data["shop_name"],
        description=data.get("description"),
        profile_image=data.get("profile_image"),
        background_image=data.get("background_image"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        address=data.get("address"),
        city=data.get("city"),
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return _shop_api(shop)


def update_shop(db: Session, shop_id: str, owner_id: str, data: dict[str, Any]) -> dict[str, Any]:
    shop = db.query(MarketShop).filter(MarketShop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if shop.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the shop owner can update this shop")
    for field in ("shop_name", "description", "profile_image", "background_image", "lat", "lng", "address", "city"):
        if field in data and data[field] is not None:
            setattr(shop, field, data[field])
    db.commit()
    db.refresh(shop)
    return _shop_api(shop)


def create_product(db: Session, shop_id: str, owner_id: str, data: dict[str, Any]) -> dict[str, Any]:
    shop = db.query(MarketShop).filter(MarketShop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if shop.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the shop owner can add products")
    product = MarketProduct(
        shop_id=shop_id,
        name=data["name"],
        price=data.get("price", 0),
        category=data.get("category", "General"),
        description=data.get("description"),
        in_stock=data.get("in_stock", True),
        image_url=data.get("image_url"),
        keywords=",".join(data["keywords"]) if data.get("keywords") else None,
    )
    db.add(product)
    db.flush()

    for i, img_url in enumerate(data.get("images", [])):
        db.add(MarketProductImage(product_id=product.id, image_url=img_url, sort_order=i))

    for v in data.get("variants", []):
        db.add(MarketProductVariant(
            product_id=product.id,
            image=v.get("image"),
            size=v.get("size"),
            color=v.get("color"),
            shape=v.get("shape"),
        ))

    db.commit()
    db.refresh(product)
    return _product_api(product)


def update_product(db: Session, product_id: str, owner_id: str, data: dict[str, Any]) -> dict[str, Any]:
    product = db.query(MarketProduct).filter(MarketProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    shop = db.query(MarketShop).filter(MarketShop.id == product.shop_id).first()
    if not shop or shop.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the shop owner can update this product")
    for field in ("name", "price", "category", "description", "in_stock", "image_url"):
        if field in data and data[field] is not None:
            setattr(product, field, data[field])
    if "keywords" in data:
        product.keywords = ",".join(data["keywords"]) if data["keywords"] else None
    db.commit()
    db.refresh(product)
    return _product_api(product)


def delete_product(db: Session, product_id: str, owner_id: str) -> None:
    product = db.query(MarketProduct).filter(MarketProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    shop = db.query(MarketShop).filter(MarketShop.id == product.shop_id).first()
    if not shop or shop.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the shop owner can delete this product")
    db.delete(product)
    db.commit()
