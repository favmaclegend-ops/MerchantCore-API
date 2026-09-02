"""Market service layer — all business logic for shops, products, ads, and categories.

All functions receive a SQLAlchemy ``Session`` bound to the market database.
"""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.market import (
    MarketAdvert,
    MarketCategory,
    MarketOrder,
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
        "source_id": p.source_id,
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


MIN_SHOPS_FOR_TOP_RATED = 10
MIN_RATING_FOR_TOP_RATED = 1000


def top_rated_shops(db: Session, limit: int = 4) -> list[dict[str, Any]]:
    total_shops = db.query(func.count(MarketShop.id)).scalar() or 0
    if total_shops < MIN_SHOPS_FOR_TOP_RATED:
        return []
    shops = (
        db.query(MarketShop)
        .filter(MarketShop.rating >= MIN_RATING_FOR_TOP_RATED)
        .order_by(MarketShop.rating.desc())
        .limit(limit)
        .all()
    )
    if len(shops) < limit:
        return []
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

    source_id = data.get("source_id")
    if source_id:
        duplicate = (
            db.query(MarketProduct)
            .filter(
                MarketProduct.shop_id == shop_id,
                MarketProduct.source_id == source_id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This item is already uploaded to your shop",
            )

    product = MarketProduct(
        shop_id=shop_id,
        source_id=source_id,
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


def _owner_org_id(owner_id: str) -> str | None:
    """Extract the organisation id from an ``org:<id>`` owner key."""
    if owner_id and owner_id.startswith("org:"):
        return owner_id[4:]
    return None


def _order_api(order: MarketOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "buyer_id": order.buyer_id,
        "buyer_name": order.buyer_name,
        "buyer_email": order.buyer_email,
        "shop_id": order.shop_id,
        "org_id": order.org_id,
        "status": order.status,
        "payment_method": order.payment_method,
        "subtotal": order.subtotal,
        "tax": order.tax,
        "total": order.total,
        "items": json.loads(order.items) if order.items else [],
        "delivery_name": order.delivery_name,
        "delivery_phone": order.delivery_phone,
        "delivery_address": order.delivery_address,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


def create_order(
    db: Session,
    *,
    shop_id: str,
    buyer_id: str,
    buyer_name: str,
    buyer_email: str,
    items: list[dict[str, Any]],
    payment_method: str,
    subtotal: float,
    tax: float,
    total: float,
    delivery_name: str | None = None,
    delivery_phone: str | None = None,
    delivery_address: str | None = None,
) -> dict[str, Any]:
    shop = db.query(MarketShop).filter(MarketShop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    org_id = _owner_org_id(shop.owner_id)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This shop cannot receive orders",
        )
    order = MarketOrder(
        buyer_id=buyer_id,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        shop_id=shop_id,
        org_id=org_id,
        status="pending",
        payment_method=payment_method,
        subtotal=round(subtotal, 2),
        tax=round(tax, 2),
        total=round(total, 2),
        items=json.dumps(items),
        delivery_name=delivery_name,
        delivery_phone=delivery_phone,
        delivery_address=delivery_address,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _order_api(order)


def list_buyer_orders(
    db: Session,
    buyer_id: str,
    status_filter: str | None = None,
) -> dict[str, Any]:
    q = db.query(MarketOrder).filter(MarketOrder.buyer_id == buyer_id)
    if status_filter:
        q = q.filter(MarketOrder.status == status_filter)
    rows = q.order_by(MarketOrder.created_at.desc()).all()
    return {"orders": [_order_api(o) for o in rows], "total": len(rows)}


def list_org_orders(
    db: Session,
    org_id: str,
    status_filter: str | None = None,
) -> dict[str, Any]:
    q = db.query(MarketOrder).filter(MarketOrder.org_id == org_id)
    if status_filter:
        q = q.filter(MarketOrder.status == status_filter)
    rows = q.order_by(MarketOrder.created_at.desc()).all()
    return {"orders": [_order_api(o) for o in rows], "total": len(rows)}


def _load_shop(db: Session, shop_id: str, org_id: str) -> MarketShop:
    shop = db.query(MarketShop).filter(MarketShop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if _owner_org_id(shop.owner_id) != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised for this order")
    return shop


def _load_order(db: Session, order_id: str) -> MarketOrder:
    order = db.query(MarketOrder).filter(MarketOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _apply_stock_changes(db: Session, app_db: Session, order: MarketOrder) -> None:
    """Decrement stock on the org inventory product for every completed line.

    MarketProduct.source_id is the org product id, so we can synchronise the
    market listing's availability from the org database on completion.
    """
    from app.models.org_commerce import OrgProduct

    items = json.loads(order.items) if order.items else []
    for line in items:
        market_product_id = line.get("product_id")
        source_id = line.get("source_id")
        quantity = int(line.get("quantity") or 1)
        if source_id and app_db is not None:
            org_product = app_db.query(OrgProduct).filter(OrgProduct.id == source_id).first()
            if org_product:
                remaining = max(0, (org_product.stock or 0) - quantity)
                org_product.stock = remaining
                if remaining <= 0:
                    org_product.status = "out-of-stock"
                if market_product_id:
                    market_product = db.query(MarketProduct).filter(MarketProduct.id == market_product_id).first()
                    if market_product:
                        market_product.in_stock = remaining > 0


def complete_order(
    db: Session,
    app_db: Session,
    org_id: str,
    member,
    order_id: str,
) -> dict[str, Any]:
    """Mark a pending order completed on scan. Writes a POS sale into the org
    database so the org dashboard totals update, and notifies both sides."""
    order = _load_order(db, order_id)
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order has already been processed",
        )
    _load_shop(db, order.shop_id, org_id)

    order.status = "completed"
    order.completed_at = datetime.now(UTC)
    db.commit()

    _apply_stock_changes(db, app_db, order)

    items = json.loads(order.items) if order.items else []
    from app.models.org_commerce import OrgPosTransaction
    from app.services.org_notification import create_notification

    txn = OrgPosTransaction(
        org_id=org_id,
        type="sale",
        customer_name=order.buyer_name,
        amount=order.total,
        status="completed",
        items=", ".join(f"{i.get('quantity')}x {i.get('name')}" for i in items),
        line_items=json.dumps(items),
        payment_method=order.payment_method or "Market",
    )
    app_db.add(txn)
    app_db.flush()

    # Record the net (tax-exclusive) sale revenue in the org ledger and accrue
    # the collected VAT into the org's tax compliance obligations. This keeps
    # market orders wired into the Finance & Accounting module.
    from app.services.org_ui import _post_ledger, accrue_sales_tax

    from app.models.organisation import Organisation

    org = app_db.query(Organisation).get(org_id)
    if org is not None:
        _post_ledger(
            app_db,
            org,
            category="income",
            account="Market Sales",
            description=f"Market order {order.id[:8]} from {order.buyer_name}",
            amount=order.subtotal,
            reference=f"MK-{order.id[:8]}",
        )
        accrue_sales_tax(app_db, org, net=order.subtotal, tax=order.tax)

    create_notification(
        app_db,
        org_id=org_id,
        kind="market_order",
        title="Market order completed",
        message=f"{order.buyer_name} completed a market order of {order.total:,.2f}.",
        severity="success",
        amount=order.total,
        actor_name=order.buyer_name,
        actor_role="Customer",
        ref=order.id,
    )

    try:
        from app.models.notification import Notification

        app_db.add(
            Notification(
                type="market_order",
                title="Order completed",
                message=f"Your market order {order.id[:8]} was completed by the shop.",
                link=None,
                is_read=False,
            )
        )
    except Exception:
        pass

    app_db.commit()
    db.refresh(order)
    return _order_api(order)


def cancel_order(
    db: Session,
    app_db: Session,
    org_id: str,
    member,
    order_id: str,
) -> dict[str, Any]:
    order = _load_order(db, order_id)
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending orders can be cancelled",
        )
    _load_shop(db, order.shop_id, org_id)

    order.status = "cancelled"
    db.commit()
    db.refresh(order)

    from app.services.org_notification import create_notification

    create_notification(
        app_db,
        org_id=org_id,
        kind="market_order",
        title="Market order cancelled",
        message=f"Market order {order.id[:8]} was cancelled.",
        severity="warning",
        actor_name=member.full_name,
        actor_role=member.role,
        ref=order.id,
    )
    return _order_api(order)


def delete_order(db: Session, order_id: str) -> dict[str, Any]:
    """Hard-delete a market order row."""
    order = _load_order(db, order_id)
    db.delete(order)
    db.commit()
    return {"message": "Order deleted", "order_id": order_id}
