from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.cache import transaction_list_cache
from app.db.session import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionResponse

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(db: Session = Depends(get_db)) -> list:
    cached = transaction_list_cache.get("all")
    if cached is not None:
        return cached
    items = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(20).all()
    transaction_list_cache["all"] = items
    return items


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
def create_transaction(transaction_in: TransactionCreate, db: Session = Depends(get_db)) -> Transaction:
    transaction = Transaction(**transaction_in.model_dump())
    db.add(transaction)
    db.commit()
    transaction_list_cache.pop("all", None)
    return transaction
