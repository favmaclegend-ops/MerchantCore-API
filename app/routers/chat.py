"""Chat HTTP API — end-to-end encrypted conversations.

Two kinds of account participate:

  * **Buyer**  : a personal user  -> participant key ``user:<id>``
  * **Owner**  : an org member     -> participant key ``org:<org_id>``

Messages are never stored in cleartext. Clients upload their RSA public key and
the server only ever stores ciphertext plus public-key-wrapped thread keys.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.chat_session import get_chat_db
from app.db.session import get_db
from app.models.organisation import OrgMember
from app.models.user import User
from app.services import chat, chat_keys

router = APIRouter(prefix="/chat", tags=["chat"])

ChatDb = Annotated[Session, Depends(get_chat_db)]
AppDb = Annotated[Session, Depends(get_db)]


@dataclass
class ChatActor:
    participant_key: str
    name: str
    role: str  # "buyer" | "owner"


def get_chat_actor(
    authorization: str,
    app_db: Session,
) -> ChatActor:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")
    payload = decode_access_token(authorization.replace("Bearer ", "", 1))
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    typ = payload.get("typ")
    if typ in (None, "user"):
        email = payload.get("sub")
        user = app_db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return ChatActor(participant_key=f"user:{user.id}", name=user.full_name, role="buyer")

    if typ == "member":
        member_id = payload.get("sub")
        org_id = payload.get("org_id")
        member = (
            app_db.query(OrgMember)
            .filter(OrgMember.id == member_id, OrgMember.org_id == org_id)
            .first()
        )
        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        return ChatActor(participant_key=f"org:{org_id}", name=member.full_name, role="owner")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# --------------------------------------------------------------------------- #
# Keys
# --------------------------------------------------------------------------- #
@router.post("/keys")
def register_key(
    body: Annotated[dict, Body()],
    db: ChatDb,
    app_db: AppDb,
    authorization: str = Header(...),
) -> dict:
    actor = get_chat_actor(authorization, app_db)
    public_key_pem = (body.get("public_key_pem") or "").strip()
    if not public_key_pem:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing public key")
    row = chat_keys.register_public_key(db, actor.participant_key, public_key_pem)
    return {"participant_key": row.participant_key}


@router.get("/keys/{participant_key}")
def get_key(participant_key: str, db: ChatDb, app_db: AppDb, authorization: str = Header(...)) -> dict:
    get_chat_actor(authorization, app_db)  # auth required
    public_key = chat_keys.get_public_key(db, participant_key)
    if not public_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public key not registered")
    return {"participant_key": participant_key, "public_key_pem": public_key}


# --------------------------------------------------------------------------- #
# Threads
# --------------------------------------------------------------------------- #
@router.post("/threads")
def create_thread(
    body: Annotated[dict, Body()],
    db: ChatDb,
    app_db: AppDb,
    authorization: str = Header(...),
) -> dict:
    actor = get_chat_actor(authorization, app_db)
    if actor.role != "buyer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only buyers create shop threads")

    shop_id = (body.get("shop_id") or "").strip()
    shop_name = (body.get("shop_name") or "").strip()
    owner_key = (body.get("owner_key") or "").strip()
    if not shop_id or not shop_name or not owner_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="shop_id, shop_name and owner_key are required",
        )

    buyer_public = chat_keys.get_public_key(db, actor.participant_key)
    if not buyer_public:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Register your encryption key (POST /chat/keys) before starting a chat",
        )
    owner_public = chat_keys.get_public_key(db, owner_key)

    return chat.open_thread(
        db,
        buyer_key=actor.participant_key,
        buyer_name=actor.name,
        shop_id=shop_id,
        shop_name=shop_name,
        shop_image=(body.get("shop_image") or "") or None,
        owner_key=owner_key,
        buyer_public_key=buyer_public,
        owner_public_key=owner_public,
    )


@router.get("/threads")
def list_threads(db: ChatDb, app_db: AppDb, authorization: str = Header(...)) -> dict:
    actor = get_chat_actor(authorization, app_db)
    return {"threads": chat.list_threads(db, actor.participant_key)}


@router.get("/threads/{thread_id}/messages")
def get_messages(thread_id: str, db: ChatDb, app_db: AppDb, authorization: str = Header(...)) -> dict:
    actor = get_chat_actor(authorization, app_db)
    thread, messages = chat.list_messages(db, thread_id=thread_id, participant_key=actor.participant_key)
    return {"thread": thread, "messages": messages}


@router.post("/threads/{thread_id}/messages")
def send_message(
    thread_id: str,
    body: Annotated[dict, Body()],
    db: ChatDb,
    app_db: AppDb,

    authorization: str = Header(...),
) -> dict:
    actor = get_chat_actor(authorization, app_db)
    text = (body.get("text") or "").strip()
    message_type= (body.get("message-type") or "").strip()
    message_image_url = (body.get("message-img-url") or "").strip()
    product_id = (body.get("product-id") or "").strip()
    old_price = (body.get("old-price") or "").strip()
    new_price = (body.get("new-price") or "").strip()
    discount_link = (body.get("discount-link") or "").strip()
    thread_key = (body.get("thread_key") or "").strip()

    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message text is required")
    if not thread_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="thread_key is required")

    message = chat.send_encrypted_message(
        db,
        thread_id=thread_id,
        sender_key=actor.participant_key,
        thread_key_b64=thread_key,
        plaintext=text,
        message_image_url=message_image_url,
        message_type=message_type,
        product_id=product_id,
        old_price=old_price,
        new_price=new_price,
        discount_link=discount_link
    )
    return {"message": message}


@router.post("/threads/{thread_id}/read")
def mark_read(thread_id: str, db: ChatDb, app_db: AppDb, authorization: str = Header(...)) -> dict:
    actor = get_chat_actor(authorization, app_db)
    return chat.mark_read(db, thread_id=thread_id, participant_key=actor.participant_key)


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, db: ChatDb, app_db: AppDb, authorization: str = Header(...)) -> dict:
    actor = get_chat_actor(authorization, app_db)
    chat.delete_thread(db, thread_id=thread_id, participant_key=actor.participant_key)
    return {"message": "Thread deleted"}


@router.patch("/threads/{thread_id}/messages/{message_id}")
def delete_message(
    thread_id: str,
    message_id: str,
    db: ChatDb,
    app_db: AppDb,
    authorization: str = Header(...),
) -> dict:
    actor = get_chat_actor(authorization, app_db)
    return chat.delete_message(
        db,
        thread_id=thread_id,
        message_id=message_id,
        participant_key=actor.participant_key,
    )
