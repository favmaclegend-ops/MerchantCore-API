from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import credit_list_cache
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.credit_entry import CreditEntry
from app.models.user import User
from app.schemas.credit_entry import CreditEntryCreate, CreditEntryResponse, CreditEntryUpdate
from app.services.notification import notify_credit_payment

router = APIRouter(tags=["credit"])


def _cache_key(user_id: str) -> str:
    return f"user_{user_id}"


@router.get("/credit-entries", response_model=list[CreditEntryResponse])
def list_credit_entries(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list:
    cache_key = _cache_key(user.id)
    cached = credit_list_cache.get(cache_key)
    if cached is not None:
        return cached
    items = (
        db.query(CreditEntry)
        .filter(CreditEntry.user_id == user.id)
        .order_by(CreditEntry.created_at.desc())
        .all()
    )
    credit_list_cache[cache_key] = items
    return items


@router.post("/credit-entries", response_model=CreditEntryResponse, status_code=201)
def create_credit_entry(
    entry_in: CreditEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CreditEntry:
    entry = CreditEntry(user_id=user.id, **entry_in.model_dump())
    db.add(entry)
    db.commit()
    credit_list_cache.pop(_cache_key(user.id), None)
    return entry


@router.patch("/credit-entries/{entry_id}", response_model=CreditEntryResponse)
def update_credit_entry(
    entry_id: str,
    entry_in: CreditEntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CreditEntry:
    entry = (
        db.query(CreditEntry)
        .filter(CreditEntry.id == entry_id, CreditEntry.user_id == user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit entry not found")
    old_balance = entry.balance
    update_data = entry_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)
    db.commit()

    if "balance" in update_data and update_data["balance"] < old_balance:
        paid = old_balance - update_data["balance"]
        notify_credit_payment(db, user.id, entry.customer_name, paid, entry.id)

    credit_list_cache.pop(_cache_key(user.id), None)
    return entry
