"""Reusable end-to-end encryption primitives for Market Chat.

The chat stores only ciphertext. Each participant holds an RSA keypair whose
*private* key never leaves the client; the server keeps only public keys and
public-key-wrapped symmetric keys.

Primitives (all base64-encoded wire strings):

  * ``generate_keypair()``          -> (public_pem, private_pem)
  * ``wrap_secret(public_pem, b64)``-> RSA-OAEP ciphertext (base64)
  * ``unwrap_secret(private_pem, w)``-> the original secret (base64)
  * ``new_key()``                   -> random AES-256 key (base64)
  * ``encrypt_payload(key_b64, text)``-> (ciphertext_b64, iv_b64)
  * ``decrypt_payload(key_b64, ct_b64, iv_b64)`` -> plaintext
"""

import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32  # AES-256
IV_BYTES = 12


# --------------------------------------------------------------------------- #
# Key points (RSA)
# --------------------------------------------------------------------------- #
def generate_keypair() -> tuple[str, str]:
    """Return (public_key_pem, private_key_pem) for a participant."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return public_pem, private_pem


def _load_public(key_pem: str):
    return serialization.load_pem_public_key(key_pem.encode("utf-8"))


def _load_private(key_pem: str):
    return serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)


def wrap_secret(public_key_pem: str, secret_b64: str) -> str:
    """Encrypt a base64 secret so only the holder of the matching private key
    can recover it (RSA-OAEP-SHA256)."""
    public_key = _load_public(public_key_pem)
    encrypted = public_key.encrypt(
        base64.b64decode(secret_b64),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return base64.b64encode(encrypted).decode("utf-8")


def unwrap_secret(private_key_pem: str, wrapped_b64: str) -> str:
    """Recover a base64 secret that was wrapped with the matching public key."""
    private_key = _load_private(private_key_pem)
    decrypted = private_key.decrypt(
        base64.b64decode(wrapped_b64),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return base64.b64encode(decrypted).decode("utf-8")


# --------------------------------------------------------------------------- #
# Symmetric payload (AES-256-GCM)
# --------------------------------------------------------------------------- #
def new_key() -> str:
    """Generate a fresh AES-256 key (base64)."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode("utf-8")


def encrypt_payload(key_b64: str, plaintext: str) -> tuple[str, str]:
    """Encrypt a UTF-8 plaintext with the AES key. Returns (ciphertext, iv)."""
    key = base64.b64decode(key_b64)
    iv = os.urandom(IV_BYTES)
    ciphertext = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(ciphertext).decode("utf-8"), base64.b64encode(iv).decode("utf-8")


def decrypt_payload(key_b64: str, ciphertext_b64: str, iv_b64: str) -> str:
    """Decrypt a payload produced by :func:`encrypt_payload`."""
    key = base64.b64decode(key_b64)
    iv = base64.b64decode(iv_b64)
    ciphertext = base64.b64decode(ciphertext_b64)
    plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
    return plaintext.decode("utf-8")
