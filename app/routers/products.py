from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import product_cache, product_list_cache
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services.notification import notify_low_stock

router = APIRouter(tags=["products"])


def _cache_key(user_id: str, suffix: str = "all") -> str:
    return f"user_{user_id}:{suffix}"


@router.get("/products", response_model=list[ProductResponse])
def list_products(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list:
    cache_key = _cache_key(user.id)
    cached = product_list_cache.get(cache_key)
    if cached is not None:
        return cached
    items = (
        db.query(Product)
        .filter(Product.user_id == user.id)
        .order_by(Product.created_at.desc())
        .all()
    )
    product_list_cache[cache_key] = items
    return items


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Product:
    cache_key = _cache_key(user.id, product_id)
    cached = product_cache.get(cache_key)
    if cached is not None:
        return cached
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == user.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product_cache[cache_key] = product
    return product


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_in: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Product:
    existing = db.query(Product).filter(Product.sku == product_in.sku).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SKU already exists")
    product = Product(user_id=user.id, **product_in.model_dump())
    db.add(product)
    db.commit()
    product_cache[_cache_key(user.id, product.id)] = product
    product_list_cache.pop(_cache_key(user.id), None)
    return product


@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: str,
    product_in: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == user.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    db.commit()

    if "stock" in update_data and product.stock < 10 and product.stock > 0:
        product.status = "low-stock"
        notify_low_stock(db, user.id, product.name, product.id, product.stock)
    elif "stock" in update_data and product.stock <= 0:
        product.status = "out-of-stock"

    product_cache[_cache_key(user.id, product.id)] = product
    product_list_cache.pop(_cache_key(user.id), None)
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.user_id == user.id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db.delete(product)
    db.commit()
    product_cache.pop(_cache_key(user.id, product_id), None)
    product_list_cache.pop(_cache_key(user.id), None)
