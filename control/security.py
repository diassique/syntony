"""Security primitives for the control plane.

- Passwords: argon2 hashing (``argon2-cffi``).
- Sessions: signed JWTs (``PyJWT``, HS256).
- API keys: a one-time-shown ``syn_…`` token; we store only its sha256 hash + a short prefix.
- Provider secrets (Band/LLM keys): Fernet-encrypted at rest, never persisted in plaintext.

Secrets are read from the environment so they never live in code:
``SYNTONY_JWT_SECRET`` (any string) and ``SYNTONY_FERNET_KEY`` (a urlsafe-base64 Fernet key;
generate one with ``Fernet.generate_key()`` / ``security.generate_fernet_key()``).
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from cryptography.fernet import Fernet

_ph = PasswordHasher()

API_KEY_PREFIX = "syn"
_JWT_ALG = "HS256"


# ---- passwords ----------------------------------------------------------------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (Argon2Error, ValueError):
        return False


# ---- session tokens (JWT) ------------------------------------------------------
def _jwt_secret() -> str:
    secret = os.environ.get("SYNTONY_JWT_SECRET")
    if not secret:
        raise RuntimeError("SYNTONY_JWT_SECRET is not set (needed to sign session tokens).")
    return secret


def issue_token(*, user_id: str, org_id: str | None = None, ttl_hours: int = 24) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org": org_id,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALG)


def verify_token(token: str) -> dict[str, Any] | None:
    """Return the decoded claims, or ``None`` if the token is invalid/expired."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None


# ---- API keys ------------------------------------------------------------------
def generate_api_key() -> tuple[str, str, str]:
    """Return ``(full_key, prefix, key_hash)``. ``full_key`` is shown to the user ONCE;
    only ``prefix`` (for display/lookup) and ``key_hash`` are stored."""
    full = f"{API_KEY_PREFIX}_{secrets.token_urlsafe(32)}"
    return full, full[:12], hash_api_key(full)


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


# ---- provider-secret encryption (Fernet) --------------------------------------
def _fernet() -> Fernet:
    key = os.environ.get("SYNTONY_FERNET_KEY")
    if not key:
        raise RuntimeError("SYNTONY_FERNET_KEY is not set (needed to encrypt provider secrets).")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def generate_fernet_key() -> str:
    """Generate a fresh Fernet key (for seeding SYNTONY_FERNET_KEY in .env)."""
    return Fernet.generate_key().decode()
