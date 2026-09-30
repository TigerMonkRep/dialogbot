"""Envelope encryption for stored credentials (integration tokens, webhook secrets, PKCE verifiers).

Each secret is encrypted with its own random 256-bit data key (AES-256-GCM); the data key is wrapped with the
key-encryption key from the environment (AES key wrap, RFC 3394). Only the wrapped data key, the nonce and the
ciphertext are stored, tagged with a fingerprint of the KEK, so the KEK can be rotated: new writes use
CREDENTIALS_KEY, old rows still decrypt with CREDENTIALS_KEY_PREVIOUS until they are re-encrypted.

Nothing here logs. The plaintext never leaves the caller that asked for it, and `Envelope` has no readable repr.
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import InvalidUnwrap, aes_key_unwrap, aes_key_wrap

from app.config import get_settings

FORMAT_V1 = b"\x01"
WRAPPED_LEN = 40  # 32-byte key + 8-byte integrity check
NONCE_LEN = 12


class CredentialsKeyUnavailable(RuntimeError):
    """The KEK that encrypted this row is not configured (rotated away or never set)."""


class DecryptFailed(RuntimeError):
    """Corrupt or tampered ciphertext."""


def _decode_key(raw: str, name: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw.strip() + "=" * (-len(raw.strip()) % 4))
    except ValueError as e:
        raise ValueError(f"{name} is not valid base64") from e
    if len(key) != 32:
        raise ValueError(f"{name} must decode to exactly 32 bytes")
    return key


def fingerprint(kek: bytes) -> str:
    return hashlib.sha256(b"dialogbot-kek:" + kek).hexdigest()[:16]


def _keys() -> dict[str, bytes]:
    """Fingerprint → KEK for every key this process may decrypt with; the first entry is used for new writes."""
    s = get_settings()
    out: dict[str, bytes] = {}
    if s.credentials_key:
        k = _decode_key(s.credentials_key, "CREDENTIALS_KEY")
        out[fingerprint(k)] = k
    elif s.app_env not in ("dev", "test"):
        raise CredentialsKeyUnavailable("CREDENTIALS_KEY is not configured")
    else:
        # dev/test only: derive a stable key from SECRET_KEY so API and worker in one .env share it.
        k = hashlib.sha256(b"dialogbot-credentials:" + (s.secret_key or "").encode()).digest()
        out[fingerprint(k)] = k
    if s.credentials_key_previous:
        k = _decode_key(s.credentials_key_previous, "CREDENTIALS_KEY_PREVIOUS")
        out.setdefault(fingerprint(k), k)
    return out


def current_key_version() -> str:
    return next(iter(_keys()))


@dataclass(frozen=True)
class Envelope:
    key_version: str
    blob: bytes  # FORMAT_V1 + wrapped_dek + nonce + ciphertext

    def __repr__(self) -> str:  # never print key material or ciphertext
        return f"Envelope(key_version={self.key_version!r}, bytes={len(self.blob)})"


def encrypt(plaintext: bytes, *, aad: bytes = b"") -> Envelope:
    keys = _keys()
    version, kek = next(iter(keys.items()))
    dek = os.urandom(32)
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(dek).encrypt(nonce, plaintext, version.encode() + b"|" + aad)
    return Envelope(version, FORMAT_V1 + aes_key_wrap(kek, dek) + nonce + ct)


def decrypt(env: Envelope, *, aad: bytes = b"") -> bytes:
    kek = _keys().get(env.key_version)
    if kek is None:
        raise CredentialsKeyUnavailable(env.key_version)
    if not env.blob.startswith(FORMAT_V1) or len(env.blob) < 1 + WRAPPED_LEN + NONCE_LEN + 16:
        raise DecryptFailed("unknown format")
    body = env.blob[1:]
    wrapped, nonce, ct = body[:WRAPPED_LEN], body[WRAPPED_LEN:WRAPPED_LEN + NONCE_LEN], body[WRAPPED_LEN + NONCE_LEN:]
    try:
        dek = aes_key_unwrap(kek, wrapped)
        return AESGCM(dek).decrypt(nonce, ct, env.key_version.encode() + b"|" + aad)
    except (InvalidUnwrap, InvalidTag, ValueError) as e:
        raise DecryptFailed("ciphertext rejected") from e


def generate_key() -> str:
    """A fresh CREDENTIALS_KEY value (base64url, 32 bytes) for the operator to put in the environment."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
