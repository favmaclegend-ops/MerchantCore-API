import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.cache import sale_list_cache
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.product import Product
from app.models.sale import Sale
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.sale import SaleCreate, SaleResponse
from app.services.notification import notify_low_stock, notify_new_sale

router = APIRouter(tags=["pos"])


@router.post("/pos/checkout", response_model=SaleResponse, status_code=201)
def checkout(
    sale_in: SaleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Sale:
    items_json = json.dumps([item.model_dump() for item in sale_in.items])
    sale = Sale(
        user_id=user.id,
        items=items_json,
        total=sale_in.total,
        payment_method=sale_in.payment_method,
        status="completed",
    )
    db.add(sale)
    db.commit()

    for item in sale_in.items:
        product = (
            db.query(Product)
            .filter(Product.id == item.id, Product.user_id == user.id)
            .first()
        )
        if product:
            product.stock -= item.quantity
            if product.stock <= 0:
                product.status = "out-of-stock"
                product.stock = 0
            elif product.stock < 10:
                product.status = "low-stock"
                notify_low_stock(db, user.id, product.name, product.id, product.stock)

    txn = Transaction(
        user_id=user.id,
        type="sale",
        customer_name="POS Sale",
        amount=sale_in.total,
        status="completed",
        items=sale_in.payment_method,
    )
    db.add(txn)
    db.commit()

    notify_new_sale(db, user.id, sale_in.total, sale.id)

    sale_list_cache.pop(f"user_{user.id}", None)
    return sale
