import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.cache import sale_list_cache
from app.db.session import get_db
from app.models.product import Product
from app.models.sale import Sale
from app.models.transaction import Transaction
from app.schemas.sale import DashboardStats, SaleCreate, SaleResponse
from app.services.notification import notify_low_stock, notify_new_sale

router = APIRouter(tags=["pos"])


@router.post("/pos/checkout", response_model=SaleResponse, status_code=201)
def checkout(sale_in: SaleCreate, db: Session = Depends(get_db)) -> Sale:
    items_json = json.dumps([item.model_dump() for item in sale_in.items])
    sale = Sale(
        items=items_json,
        total=sale_in.total,
        payment_method=sale_in.payment_method,
        status="completed",
    )
    db.add(sale)
    db.commit()

    for item in sale_in.items:
        product = db.query(Product).filter(Product.id == item.id).first()
        if product:
            product.stock -= item.quantity
            if product.stock <= 0:
                product.status = "out-of-stock"
                product.stock = 0
            elif product.stock < 10:
                product.status = "low-stock"
                notify_low_stock(db, product.name, product.id, product.stock)

    txn = Transaction(
        type="sale",
        customer_name="POS Sale",
        amount=sale_in.total,
        status="completed",
        items=sale_in.payment_method,
    )
    db.add(txn)
    db.commit()

    notify_new_sale(db, sale_in.total, sale.id)

    sale_list_cache.pop("all", None)
    return sale
