from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.cache import credit_list_cache
from app.db.session import get_db
from app.models.credit_entry import CreditEntry
from app.schemas.credit_entry import CreditEntryCreate, CreditEntryResponse, CreditEntryUpdate
from app.services.notification import notify_credit_payment

router = APIRouter(tags=["credit"])


@router.get("/credit-entries", response_model=list[CreditEntryResponse])
def list_credit_entries(db: Session = Depends(get_db)) -> list:
    cached = credit_list_cache.get("all")
    if cached is not None:
        return cached
    items = db.query(CreditEntry).order_by(CreditEntry.created_at.desc()).all()
    credit_list_cache["all"] = items
    return items


@router.post("/credit-entries", response_model=CreditEntryResponse, status_code=201)
def create_credit_entry(entry_in: CreditEntryCreate, db: Session = Depends(get_db)) -> CreditEntry:
    entry = CreditEntry(**entry_in.model_dump())
    db.add(entry)
    db.commit()
    credit_list_cache.pop("all", None)
    return entry


@router.patch("/credit-entries/{entry_id}", response_model=CreditEntryResponse)
def update_credit_entry(entry_id: str, entry_in: CreditEntryUpdate, db: Session = Depends(get_db)) -> CreditEntry:
    entry = db.query(CreditEntry).filter(CreditEntry.id == entry_id).first()
    if not entry:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit entry not found")
    old_balance = entry.balance
    update_data = entry_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)
    db.commit()

    if "balance" in update_data and update_data["balance"] < old_balance:
        paid = old_balance - update_data["balance"]
        notify_credit_payment(db, entry.customer_name, paid, entry.id)

    credit_list_cache.pop("all", None)
    return entry
