"""Market HTTP API — public browsing + authenticated shop management.

Public endpoints require no auth so any client platform can browse.
Authenticated endpoints require a valid org member JWT (owner-only checks
are done inside the service layer).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import decrypt_token, encrypt_token, get_current_member, get_current_user
from app.db.market_session import get_market_db
from app.db.session import get_db
from app.models.organisation import OrgMember, Organisation
from app.models.user import User
from app.services import market
from app.services.org_notification import create_notification
from app.services.org_ui import _post_ledger

router = APIRouter(prefix="/market", tags=["market"])

MarketDb = Annotated[Session, Depends(get_market_db)]
MemberDep = Annotated[OrgMember, Depends(get_current_member)]
AppDb = Annotated[Session, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


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


@router.get("/services")
def list_services(
    db: MarketDb,
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(60, ge=1, le=100),
) -> dict:
    return market.list_services(db, search=search, page=page, limit=limit)


@router.get("/services/{service_id}")
def get_service(service_id: str, db: MarketDb) -> dict:
    return market.get_service(db, service_id)


@router.put("/services/{service_id}/rate")
def rate_service(
    service_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
) -> dict:
    stars = body.get("stars")
    rater = body.get("rater")
    return market.rate_service(
        db,
        service_id=service_id,
        stars=float(stars) if stars is not None else 0,
        rater_key=str(rater or ""),
    )


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

def _owner_key(member: OrgMember) -> str:
    """Build the cross-platform owner key used to identify shop ownership."""
    return f"org:{member.org_id}"


@router.post("/shops")
def create_shop(body: Annotated[dict, Body()], db: MarketDb, member: MemberDep) -> dict:
    return market.create_shop(db, owner_id=_owner_key(member), data=body)


@router.patch("/shops/{shop_id}")
def update_shop(
    shop_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.update_shop(db, shop_id=shop_id, owner_id=_owner_key(member), data=body)


@router.post("/shops/{shop_id}/products")
def create_product(
    shop_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.create_product(db, shop_id=shop_id, owner_id=_owner_key(member), data=body)


@router.patch("/products/{product_id}")
def update_product(
    product_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.update_product(db, product_id=product_id, owner_id=_owner_key(member), data=body)


@router.delete("/products/{product_id}")
def delete_product(product_id: str, db: MarketDb, member: MemberDep) -> dict:
    market.delete_product(db, product_id=product_id, owner_id=_owner_key(member))
    return {"message": "Product deleted"}


@router.post("/shops/{shop_id}/services")
def create_service(
    shop_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    member: MemberDep,
) -> dict:
    return market.create_service(db, shop_id=shop_id, owner_id=_owner_key(member), data=body)


@router.delete("/services/{service_id}")
def delete_service(service_id: str, db: MarketDb, member: MemberDep) -> dict:
    market.delete_service(db, service_id=service_id, owner_id=_owner_key(member))
    return {"message": "Service removed from market"}


# ---------------------------------------------------------------------------
# Service requests (customer → org)
# ---------------------------------------------------------------------------

@router.post("/services/{service_id}/requests")
def create_service_request(
    service_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
) -> dict:
    """Public — a visitor requests a service from a shop.

    A logged-in buyer also supplies ``user_id`` so the org's response can be
    delivered into their encrypted in-app inbox.
    """
    name = (body.get("requester_name") or "").strip()
    phone = (body.get("requester_phone") or "").strip()
    if not name or not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name and phone are required")
    return market.create_service_request(
        db,
        service_id=service_id,
        requester_name=name,
        requester_phone=phone,
        requester_email=(body.get("requester_email") or "").strip() or None,
        requester_address=(body.get("requester_address") or "").strip() or None,
        user_id=(body.get("user_id") or "").strip() or None,
        note=(body.get("note") or "").strip() or None,
    )


@router.get("/services/requests/org")
def org_service_requests(
    db: MarketDb,
    member: MemberDep,
    status: str | None = Query(None),
) -> dict:
    return market.list_org_service_requests(db, org_id=member.org_id, status_filter=status)


@router.put("/services/requests/{request_id}/respond")
def respond_to_service_request(
    request_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
    org_db: AppDb,
    member: MemberDep,
) -> dict:
    response_text = (body.get("response") or "").strip()
    if not response_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Response text is required")
    new_status = body.get("status") or "responded"
    result = market.respond_to_service_request(
        db,
        request_id=request_id,
        org_id=member.org_id,
        response_text=response_text,
        new_status=new_status,
    )

    # Booking revenue: when a market service request first transitions to
    # "completed", post the service price as income into the org's general
    # ledger (account "Service Sales"). This keeps the service-income figure
    # and the total revenue dashboard aligned with the permanent ledger.
    if result.get("_completed"):
        amount = round(float(result.get("_service_price") or 0.0), 2)
        org = org_db.query(Organisation).filter(Organisation.id == member.org_id).first()
        if org is not None and amount > 0:
            _post_ledger(
                org_db,
                org,
                category="income",
                account="Service Sales",
                description=(
                    f"Service request completed: "
                    f"{result.get('service_name') or 'service'} "
                    f"for {result.get('requester_name')}"
                ),
                amount=amount,
                reference=request_id,
            )
            create_notification(
                org_db,
                org_id=member.org_id,
                kind="service",
                title="Service request completed",
                message=(
                    f"Request for {result.get('service_name') or 'service'} "
                    f"({result.get('requester_name')}) completed — {amount} "
                    f"booked to Service Sales."
                ),
                severity="success",
                amount=amount,
                ref=request_id,
                actor_name=member.full_name,
                actor_role=member.role,
            )
            org_db.commit()

    result.pop("_completed", None)
    result.pop("_service_price", None)
    return result


@router.delete("/services/requests/{request_id}")
def delete_service_request(request_id: str, db: MarketDb, member: MemberDep) -> dict:
    """Delete a completed service request (org side, admin-only)."""
    return market.delete_service_request(db, request_id=request_id, org_id=member.org_id)


# ---------------------------------------------------------------------------
# Market orders (buyer = personal user JWT)
# ---------------------------------------------------------------------------

@router.post("/orders")
def place_orders(body: Annotated[dict, Body()], db: MarketDb, user: UserDep) -> dict:
    """Place one order per shop group. Each group may hit a different shop.

    Body: ``{"groups": [{shop_id, items, subtotal, tax, total, payment_method}]}``
    """
    groups = body.get("groups") or []
    if not groups:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot checkout an empty cart")

    buyer_name = user.full_name or user.username or user.email
    placed: list[dict] = []
    alerts: list[dict] = []
    for group in groups:
        shop_id = group.get("shop_id")
        if not shop_id:
            continue
        order = market.create_order(
            db,
            shop_id=shop_id,
            buyer_id=user.id,
            buyer_name=buyer_name,
            buyer_email=user.email,
            items=group.get("items") or [],
            payment_method=group.get("payment_method") or "Cash",
            subtotal=group.get("subtotal") or 0,
            tax=group.get("tax") or 0,
            total=group.get("total") or 0,
            delivery_name=(group.get("delivery_name") or "").strip() or None,
            delivery_phone=(group.get("delivery_phone") or "").strip() or None,
            delivery_address=(group.get("delivery_address") or "").strip() or None,
        )
        placed.append(order)
        shop = market._load_shop(db, shop_id, order["org_id"])
        alerts.append(
            {
                "shop_id": shop_id,
                "shop_name": shop.shop_name,
                "message": f"New market order · {len(group.get('items') or [])} item(s)",
                "amount": group.get("total") or 0,
                "sentAt": order["created_at"],
            }
        )
    return {"orders": placed, "alerts": alerts}


@router.get("/orders")
def buyer_orders(db: MarketDb, user: UserDep, status: str | None = Query(None)) -> dict:
    return market.list_buyer_orders(db, buyer_id=user.id, status_filter=status)


@router.delete("/orders/{order_id}")
def delete_buyer_order(order_id: str, db: MarketDb, user: UserDep) -> dict:
    order = market._load_order(db, order_id)
    if order.buyer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised for this order",
        )
    return market.delete_order(db, order_id)


@router.get("/orders/{order_id}/qrcode")
def buyer_order_qrcode(order_id: str, db: MarketDb, user: UserDep) -> dict:
    order = market._load_order(db, order_id)
    if order.buyer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised for this order",
        )
    token = encrypt_token(order_id)
    return {"token": token, "order_id": order_id}


# ---------------------------------------------------------------------------
# Market orders (org side: Supply Chain "Orders" tab)
# ---------------------------------------------------------------------------

@router.get("/orders/org")
def org_orders(db: MarketDb, member: MemberDep, status: str | None = Query(None)) -> dict:
    return market.list_org_orders(db, org_id=member.org_id, status_filter=status)


@router.get("/orders/org/{order_id}/qrcode")
def order_qrcode(order_id: str, db: MarketDb, member: MemberDep) -> dict:
    order = market._load_order(db, order_id)
    market._load_shop(db, order.shop_id, member.org_id)
    token = encrypt_token(order_id)
    return {"token": token, "order_id": order_id}


@router.post("/orders/org/scan")
def scan_complete_order(body: Annotated[dict, Body()], db: MarketDb, app_db: AppDb, member: MemberDep) -> dict:
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code")
    order_id = decrypt_token(token)
    return market.complete_order(db, app_db, member.org_id, member, order_id)


@router.post("/orders/org/{order_id}/cancel")
def cancel_order(order_id: str, db: MarketDb, app_db: AppDb, member: MemberDep) -> dict:
    return market.cancel_order(db, app_db, member.org_id, member, order_id)


@router.delete("/orders/org/{order_id}")
def delete_org_order(order_id: str, db: MarketDb, member: MemberDep) -> dict:
    order = market._load_order(db, order_id)
    market._load_shop(db, order.shop_id, member.org_id)
    return market.delete_order(db, order_id)


# ---------------------------------------------------------------------------
# Customer inbox (buyer = personal user JWT)
# ---------------------------------------------------------------------------

@router.get("/inbox")
def customer_inbox(db: MarketDb, user: UserDep) -> dict:
    return market.list_customer_inbox(db, user_id=user.id)


@router.get("/inbox/unread")
def customer_inbox_unread(db: MarketDb, user: UserDep) -> dict:
    return {"unread": market.unread_customer_inbox_count(db, user_id=user.id)}


@router.put("/inbox/{message_id}/read")
def read_inbox_message(message_id: str, db: MarketDb, user: UserDep) -> dict:
    return market.mark_inbox_read(db, user_id=user.id, message_id=message_id)


@router.delete("/inbox")
def clear_inbox(db: MarketDb, user: UserDep) -> dict:
    return market.clear_customer_inbox(db, user_id=user.id)


@router.delete("/inbox/{message_id}")
def delete_inbox_message(message_id: str, db: MarketDb, user: UserDep) -> dict:
    return market.delete_inbox_message(db, user_id=user.id, message_id=message_id)

@router.get("/top-products")
def top_products(db: MarketDb, limit: int = Query(6, ge=1, le=20)) -> list[dict]:
    return market.list_top_products(db, limit=limit)

@router.put("/products/{product_id}/rate")
def rate_product(
    product_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
) -> dict:
    stars = body.get("stars")
    rater = body.get("rater")
    return market.rate_product(
        db,
        product_id=product_id,
        stars=float(stars) if stars is not None else 0,
        rater_key=str(rater or ""),
    )


@router.put("/shops/{shop_id}/rate")
def rate_shop(
    shop_id: str,
    body: Annotated[dict, Body()],
    db: MarketDb,
) -> dict:
    stars = body.get("stars")
    rater = body.get("rater")
    return market.rate_shop(
        db,
        shop_id=shop_id,
        stars=float(stars) if stars is not None else 0,
        rater_key=str(rater or ""),
    )
