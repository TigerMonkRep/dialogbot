"""Password hashing and opaque token helpers.

Passwords: argon2id via pwdlib (maintained library; no home-grown crypto).
Tokens: 256-bit random values from the OS CSPRNG; only SHA-256 digests are
persisted, so a database leak does not expose usable tokens.
"""
from __future__ import annotations

import hashlib
import secrets

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password, password_hash)
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()
