"""Chat service layer — thread + message business logic, encryption and TTL purge.

Everything here is a reusable function taking a SQLAlchemy ``Session`` bound to
the chat database (``app.db.chat_session.get_chat_db``). The server stores only
ciphertext plus public-key-wrapped thread keys; it never sees plaintext.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import chat_crypto
from app.models.chat import ChatMessage, ChatThread
from app.services.chat_keys import get_public_key

CHAT_TTL_DAYS = 4
CHAT_TTL_DELTA = timedelta(days=CHAT_TTL_DAYS)


# --------------------------------------------------------------------------- #
# Serialisers
# --------------------------------------------------------------------------- #
def _message_api(m: ChatMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "thread_id": m.thread_id,
        "sender_key": m.sender_key,
        "ciphertext": m.ciphertext,
        "iv": m.iv,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
    }


def _thread_api(t: ChatThread) -> dict[str, Any]:
    return {
        "id": t.id,
        "buyer_key": t.buyer_key,
        "buyer_name": t.buyer_name,
        "owner_key": t.owner_key,
        "shop_id": t.shop_id,
        "shop_name": t.shop_name,
        "shop_image": t.shop_image,
        "thread_key_wrapped_buyer": t.thread_key_wrapped_buyer,
        "thread_key_wrapped_owner": t.thread_key_wrapped_owner,
        "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
        "unread_buyer": t.unread_buyer,
        "unread_owner": t.unread_owner,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _participant_is_member(thread: ChatThread, participant_key: str) -> bool:
    return participant_key in (thread.buyer_key, thread.owner_key)


# --------------------------------------------------------------------------- #
# Thread lifecycle
# --------------------------------------------------------------------------- #
def open_thread(
    db: Session,
    *,
    buyer_key: str,
    buyer_name: str,
    shop_id: str,
    shop_name: str,
    shop_image: str | None,
    owner_key: str,
    buyer_public_key: str,
    owner_public_key: str | None,
) -> dict[str, Any]:
    """Return the thread for a buyer+shop, creating it when missing.

    On creation a fresh symmetric thread key is generated and wrapped under the
    buyer's public key (and the owner's key when available). Only the wrapped
    copies are stored — the server cannot decrypt.
    """
    purge_expired(db)

    thread = (
        db.query(ChatThread)
        .filter(ChatThread.buyer_key == buyer_key, ChatThread.shop_id == shop_id)
        .first()
    )
    if thread:
        db.refresh(thread)
        return _thread_api(thread)

    thread_key = chat_crypto.new_key()
    wrapped_buyer = chat_crypto.wrap_secret(buyer_public_key, thread_key)
    wrapped_owner = (
        chat_crypto.wrap_secret(owner_public_key, thread_key)
        if owner_public_key
        else None
    )

    thread = ChatThread(
        buyer_key=buyer_key,
        buyer_name=buyer_name,
        owner_key=owner_key,
        shop_id=shop_id,
        shop_name=shop_name,
        shop_image=shop_image,
        thread_key_wrapped_buyer=wrapped_buyer,
        thread_key_wrapped_owner=wrapped_owner,
        last_message_at=None,
        unread_buyer=0,
        unread_owner=0,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return _thread_api(thread)


def get_thread(db: Session, thread_id: str) -> ChatThread | None:
    return db.query(ChatThread).filter(ChatThread.id == thread_id).first()


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
def send_encrypted_message(
    db: Session,
    *,
    thread_id: str,
    sender_key: str,
    thread_key_b64: str,
    plaintext: str,
) -> dict[str, Any]:
    """Store a message encrypted with the supplied shared thread key.

    The client holds the thread key (unwrapped from its private key) and sends
    it over the (TLS/MITM-protected) API so the server can encrypt it at rest
    and re-wrap for any participant missing a copy. This keeps the stored data
    E2E: the key is never persisted in plaintext.
    """
    thread = get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if not _participant_is_member(thread, sender_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant of this thread")

    ciphertext, iv = chat_crypto.encrypt_payload(thread_key_b64, plaintext)
    now = datetime.now(UTC)
    message = ChatMessage(
        thread_id=thread_id,
        sender_key=sender_key,
        ciphertext=ciphertext,
        iv=iv,
        sent_at=now,
    )
    db.add(message)

    # Re-wrap the shared key for the owner if we now have their public key.
    if thread.thread_key_wrapped_owner is None:
        owner_public = get_public_key(db, thread.owner_key)
        if owner_public:
            thread.thread_key_wrapped_owner = chat_crypto.wrap_secret(owner_public, thread_key_b64)

    thread.last_message_at = now
    if participant_is_buyer(thread, sender_key):
        thread.unread_owner += 1
    else:
        thread.unread_buyer += 1

    db.commit()
    db.refresh(message)
    return _message_api(message)


def participant_is_buyer(thread: ChatThread, participant_key: str) -> bool:
    return thread.buyer_key == participant_key


def list_messages(
    db: Session,
    *,
    thread_id: str,
    participant_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (thread_api, messages_api) for a participant after pruning."""
    purge_expired(db)
    thread = get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if not _participant_is_member(thread, participant_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant of this thread")
    messages = [_message_api(m) for m in thread.messages]
    return _thread_api(thread), messages


def list_threads(db: Session, participant_key: str) -> list[dict[str, Any]]:
    """All threads for a participant, newest activity first (after pruning)."""
    purge_expired(db)
    rows = (
        db.query(ChatThread)
        .filter(
            (ChatThread.buyer_key == participant_key) | (ChatThread.owner_key == participant_key)
        )
        .all()
    )
    rows.sort(key=lambda t: t.last_message_at or t.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return [_thread_api(t) for t in rows]


def mark_read(db: Session, *, thread_id: str, participant_key: str) -> dict[str, Any]:
    thread = get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if participant_is_buyer(thread, participant_key):
        thread.unread_buyer = 0
    else:
        thread.unread_owner = 0
    db.commit()
    db.refresh(thread)
    return _thread_api(thread)


def delete_thread(db: Session, *, thread_id: str, participant_key: str) -> None:
    thread = get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if not _participant_is_member(thread, participant_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant of this thread")
    db.delete(thread)
    db.commit()


# --------------------------------------------------------------------------- #
# TTL purge (4 days)
# --------------------------------------------------------------------------- #
def purge_expired(db: Session, ttl_days: int = CHAT_TTL_DAYS) -> int:
    """Delete messages older than ``ttl_days`` and drop any thread left empty.

    Returns the number of messages removed.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=ttl_days)).replace(tzinfo=None)
    removed = 0

    all_threads = db.query(ChatThread).all()
    for thread in all_threads:
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.sent_at.desc())
            .all()
        )
        if not msgs:
            # A brand-new thread has no messages yet — keep it unless it is
            # itself stale (e.g. it aged out before ever receiving a message).
            activity = thread.last_message_at or thread.created_at
            if activity is not None and activity.replace(tzinfo=None) < cutoff:
                db.delete(thread)
            continue

        latest = msgs[0].sent_at.replace(tzinfo=None)
        if latest < cutoff:
            # Every message is past the TTL — drop the whole thread.
            for m in msgs:
                db.delete(m)
                removed += 1
            db.delete(thread)
            continue

        for m in msgs:
            if m.sent_at.replace(tzinfo=None) < cutoff:
                db.delete(m)
                removed += 1
        thread.last_message_at = msgs[0].sent_at
    db.commit()
    return removed
