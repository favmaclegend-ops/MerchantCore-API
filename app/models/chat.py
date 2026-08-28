"""Chat models — stored in the separate ``chat.db`` database.

These use ``ChatBase`` (not the main ``Base`` or ``MarketBase``) so the chat
messages live in an isolated database dedicated to encrypted conversations.

Encryption model (end-to-end):
  * Each participant (buyer ``user:<id>``, shop owner ``org:<org_id>``) has an
    RSA keypair. Only the *public* key is ever stored server-side.
  * Each thread has a random symmetric ``thread_key``. The key is stored ONLY as
    ciphertext — wrapped under each participant's RSA public key
    (``thread_key_wrapped_buyer`` / ``thread_key_wrapped_owner``).
  * Message bodies are encrypted with that symmetric ``thread_key``
    (AES-256-GCM). The server can never read them without a participant's
    private key, which never leaves the client.
  * Messages are wiped after ``CHAT_TTL_DAYS`` (4 days) by :func:`purge_expired`.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.chat_session import ChatBase
from app.models.base import BaseMixin, TimestampMixin


class ChatUserKey(ChatBase, BaseMixin):
    """A chat participant's RSA public key (registered by the client)."""

    __tablename__ = "chat_user_keys"

    participant_key = Column(String(120), unique=True, index=True, nullable=False)
    public_key_pem = Column(Text, nullable=False)


class ChatThread(ChatBase, BaseMixin, TimestampMixin):
    """A conversation between a buyer and a shop (owner)."""

    __tablename__ = "chat_threads"

    buyer_key = Column(String(120), index=True, nullable=False)
    buyer_name = Column(String(255), nullable=False)

    shop_id = Column(String(36), index=True, nullable=False)
    shop_name = Column(String(255), nullable=False)
    shop_image = Column(String(1000), nullable=True)
    owner_key = Column(String(120), index=True, nullable=False)

    # The symmetric thread key, wrapped under each participant's public key.
    thread_key_wrapped_buyer = Column(Text, nullable=False)
    thread_key_wrapped_owner = Column(Text, nullable=True)

    last_message_at = Column(DateTime, nullable=True)
    unread_buyer = Column(Integer, nullable=False, default=0)
    unread_owner = Column(Integer, nullable=False, default=0)

    messages = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sent_at",
    )


class ChatMessage(ChatBase, BaseMixin):
    """A single encrypted message in a thread."""

    __tablename__ = "chat_messages"

    thread_id = Column(String(36), ForeignKey("chat_threads.id"), nullable=False, index=True)
    sender_key = Column(String(120), nullable=False)

    # Encrypted with the thread's symmetric key (AES-256-GCM).
    ciphertext = Column(Text, nullable=False)
    iv = Column(String(64), nullable=False)

    sent_at = Column(DateTime, index=True, nullable=False)

    thread = relationship("ChatThread", back_populates="messages")
