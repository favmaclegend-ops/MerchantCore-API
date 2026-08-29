"""End-to-end tests for the encrypted Market Chat.

These verify the full E2E pipeline:
  * crypto round-trip (RSA wrap + AES-GCM payload),
  * service layer (thread creation, encrypted send, list, purge),
  * HTTP API (register key, open thread, send, list) with a real user JWT.

All DBs are isolated to this test: the app DB uses ``test.db`` and the chat DB
uses a temporary sqlite file so nothing leaks into the real databases.
"""

import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import chat_crypto
from app.core.security import create_access_token
from app.db.chat_session import ChatBase, get_chat_db
from app.db.session import Base, get_db
from app.main import app
from app.models.chat import ChatMessage
from app.models.user import User
from app.services import chat

APP_DB_URL = "sqlite:///./test.db"
app_engine = create_engine(APP_DB_URL, connect_args={"check_same_thread": False})
AppSession = sessionmaker(autocommit=False, autoflush=False, bind=app_engine)


@pytest.fixture
def chat_engine():
    _, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    ChatBase.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def chat_session(chat_engine):
    session = sessionmaker(autocommit=False, autoflush=False, bind=chat_engine)()
    try:
        yield session
    finally:
        session.close()


def make_user(email: str, username: str):
    session = AppSession()
    user = session.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            username=username,
            full_name="Test User",
            hashed_password="x",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    session.close()
    return user


def user_token(user: User) -> str:
    return create_access_token(user.email, claims={"typ": "user"})


@pytest.fixture
def client(chat_engine):
    Base.metadata.create_all(bind=app_engine)

    def _override_chat_db():
        session = sessionmaker(autocommit=False, autoflush=False, bind=chat_engine)()
        try:
            yield session
        finally:
            session.close()

    def _override_app_db():
        session = AppSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_chat_db] = _override_chat_db
    app.dependency_overrides[get_db] = _override_app_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=app_engine)


# --------------------------------------------------------------------------- #
# Crypto primitives
# --------------------------------------------------------------------------- #
def test_crypto_round_trip():
    public_pem, private_pem = chat_crypto.generate_keypair()
    key = chat_crypto.new_key()
    wrapped = chat_crypto.wrap_secret(public_pem, key)
    assert chat_crypto.unwrap_secret(private_pem, wrapped) == key

    ct, iv = chat_crypto.encrypt_payload(key, "top secret 🚀")
    assert ct != "top secret 🚀"
    assert chat_crypto.decrypt_payload(key, ct, iv) == "top secret 🚀"


def test_encryption_is_not_readable_without_key():
    public_pem, _ = chat_crypto.generate_keypair()
    key = chat_crypto.new_key()
    ct_b64, iv_b64 = chat_crypto.encrypt_payload(key, "secret")
    other_key = chat_crypto.new_key()
    with pytest.raises(Exception):
        chat_crypto.decrypt_payload(other_key, ct_b64, iv_b64)


# --------------------------------------------------------------------------- #
# Service layer
# --------------------------------------------------------------------------- #
def test_service_open_thread_and_send(chat_session):
    buyer_pub, buyer_priv = chat_crypto.generate_keypair()
    thread = chat.open_thread(
        chat_session,
        buyer_key="user:1",
        buyer_name="Buyer",
        shop_id="shop-1",
        shop_name="Kofi Fresh Mart",
        shop_image=None,
        owner_key="org:2",
        buyer_public_key=buyer_pub,
        owner_public_key=None,
    )
    assert thread["shop_name"] == "Kofi Fresh Mart"

    # Client unwraps the thread key with its private key (E2E).
    tkey = chat_crypto.unwrap_secret(buyer_priv, thread["thread_key_wrapped_buyer"])
    msg = chat.send_encrypted_message(
        chat_session,
        thread_id=thread["id"],
        sender_key="user:1",
        thread_key_b64=tkey,
        plaintext="Hello shop!",
    )
    assert msg["ciphertext"] != "Hello shop!"

    # Sender can decrypt its own sent message.
    assert chat_crypto.decrypt_payload(tkey, msg["ciphertext"], msg["iv"]) == "Hello shop!"

    _, messages = chat.list_messages(chat_session, thread_id=thread["id"], participant_key="user:1")
    assert len(messages) == 1


def test_service_owner_side(chat_session):
    buyer_pub, buyer_priv = chat_crypto.generate_keypair()
    owner_pub, owner_priv = chat_crypto.generate_keypair()
    thread = chat.open_thread(
        chat_session,
        buyer_key="user:1",
        buyer_name="Buyer",
        shop_id="shop-1",
        shop_name="Shop",
        shop_image=None,
        owner_key="org:2",
        buyer_public_key=buyer_pub,
        owner_public_key=owner_pub,
    )
    tkey = chat_crypto.unwrap_secret(buyer_priv, thread["thread_key_wrapped_buyer"])
    chat.send_encrypted_message(
        chat_session, thread_id=thread["id"], sender_key="user:1", thread_key_b64=tkey, plaintext="hi"
    )
    chat.send_encrypted_message(
        chat_session, thread_id=thread["id"], sender_key="org:2", thread_key_b64=tkey, plaintext="reply"
    )

    threads = chat.list_threads(chat_session, "org:2")
    assert len(threads) == 1
    assert threads[0]["unread_buyer"] == 1

    chat.mark_read(chat_session, thread_id=thread["id"], participant_key="user:1")
    _, messages = chat.list_messages(chat_session, thread_id=thread["id"], participant_key="org:2")
    assert len(messages) == 2
    # Owner decrypts with its own private key.
    otkey = chat_crypto.unwrap_secret(owner_priv, threads[0]["thread_key_wrapped_owner"])
    assert chat_crypto.decrypt_payload(otkey, messages[0]["ciphertext"], messages[0]["iv"]) in ("hi", "reply")


def test_ttl_purge(chat_session):
    buyer_pub, _ = chat_crypto.generate_keypair()
    thread = chat.open_thread(
        chat_session,
        buyer_key="user:1",
        buyer_name="Buyer",
        shop_id="shop-1",
        shop_name="Shop",
        shop_image=None,
        owner_key="org:2",
        buyer_public_key=buyer_pub,
        owner_public_key=None,
    )
    tkey = chat_crypto.new_key()
    chat.send_encrypted_message(
        chat_session, thread_id=thread["id"], sender_key="user:1", thread_key_b64=tkey, plaintext="old"
    )

    # Force a message to be 5 days old (past the 4-day TTL).
    msg = chat_session.query(ChatMessage).first()
    msg.sent_at = datetime.now(UTC) - timedelta(days=5)
    chat_session.commit()

    removed = chat.purge_expired(chat_session)
    assert removed >= 1
    assert chat.list_threads(chat_session, "user:1") == []


# --------------------------------------------------------------------------- #
# HTTP API
# --------------------------------------------------------------------------- #
def test_api_full_flow(client):
    user = make_user("buyer@test.com", "buyer1")
    headers = {"Authorization": f"Bearer {user_token(user)}"}
    buyer_pub, buyer_priv = chat_crypto.generate_keypair()

    # register key
    r = client.post("/api/v1/chat/keys", json={"public_key_pem": buyer_pub}, headers=headers)
    assert r.status_code == 200, r.text

    # open thread
    r = client.post(
        "/api/v1/chat/threads",
        json={"shop_id": "shop-1", "shop_name": "Kofi Fresh Mart", "owner_key": "org:2"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    thread = r.json()
    tkey = chat_crypto.unwrap_secret(buyer_priv, thread["thread_key_wrapped_buyer"])

    # send encrypted
    r = client.post(
        f"/api/v1/chat/threads/{thread['id']}/messages",
        json={"text": "Hello API!", "thread_key": tkey},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    ciphertext = r.json()["message"]["ciphertext"]
    assert ciphertext != "Hello API!"

    # list threads + messages
    r = client.get("/api/v1/chat/threads", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["threads"]) == 1

    r = client.get(f"/api/v1/chat/threads/{thread['id']}/messages", headers=headers)
    assert r.status_code == 200
    body = r.json()
    message = body["messages"][0]
    assert chat_crypto.decrypt_payload(tkey, message["ciphertext"], message["iv"]) == "Hello API!"


def test_api_requires_key_registration(client):
    user = make_user("buyer2@test.com", "buyer2")
    headers = {"Authorization": f"Bearer {user_token(user)}"}
    r = client.post(
        "/api/v1/chat/threads",
        json={"shop_id": "shop-1", "shop_name": "Shop", "owner_key": "org:2"},
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_delete_single_message(client):
    buyer_pub, buyer_priv = chat_crypto.generate_keypair()
    user = make_user("buyer-delete@example.com", "buyer-delete")
    token = user_token(user)

    key_resp = client.post("/chat/keys", json={"public_key_pem": buyer_pub}, headers={"Authorization": f"Bearer {token}"})
    assert key_resp.status_code == 200

    thread_resp = client.post(
        "/chat/threads",
        json={"shop_id": "shop-delete", "shop_name": "Delete Shop", "owner_key": "org:2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert thread_resp.status_code == 200
    thread = thread_resp.json()
    thread_key = chat_crypto.unwrap_secret(buyer_priv, thread["thread_key_wrapped_buyer"])

    send_resp = client.post(
        f"/chat/threads/{thread['id']}/messages",
        json={"text": "hello world", "thread_key": thread_key},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert send_resp.status_code == 200
    message_id = send_resp.json()["message"]["id"]

    delete_resp = client.patch(
        f"/chat/threads/{thread['id']}/messages/{message_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message_id"] == message_id

    list_resp = client.get(
        f"/chat/threads/{thread['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["messages"] == []
