"""Chat participant keys — reusable service for registering/looking up the
RSA public keys that make end-to-end encryption work.

Only public keys are stored. Private keys never reach the server.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.chat import ChatUserKey


def get_user_key(db: Session, participant_key: str) -> ChatUserKey | None:
    """Return the stored key row for a participant, or ``None``."""
    return db.query(ChatUserKey).filter(ChatUserKey.participant_key == participant_key).first()


def get_public_key(db: Session, participant_key: str) -> str | None:
    """Return a participant's public key PEM, or ``None`` if not registered."""
    row = get_user_key(db, participant_key)
    return row.public_key_pem if row else None


def register_public_key(db: Session, participant_key: str, public_key_pem: str) -> ChatUserKey:
    """Store (or replace) a participant's public key. Idempotent per key."""
    row = get_user_key(db, participant_key)
    now = datetime.now(UTC)
    if row:
        row.public_key_pem = public_key_pem
        row.updated_at = now
    else:
        row = ChatUserKey(participant_key=participant_key, public_key_pem=public_key_pem)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row
