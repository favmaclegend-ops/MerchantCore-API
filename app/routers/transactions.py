from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.cache import transaction_list_cache
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionResponse

router = APIRouter(tags=["transactions"])


def _cache_key(user_id: str) -> str:
    return f"user_{user_id}"


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list:
    cache_key = _cache_key(user.id)
    cached = transaction_list_cache.get(cache_key)
    if cached is not None:
        return cached
    items = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(20)
        .all()
    )
    transaction_list_cache[cache_key] = items
    return items


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
def create_transaction(
    transaction_in: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Transaction:
    transaction = Transaction(user_id=user.id, **transaction_in.model_dump())
    db.add(transaction)
    db.commit()
    transaction_list_cache.pop(_cache_key(user.id), None)
    return transaction
