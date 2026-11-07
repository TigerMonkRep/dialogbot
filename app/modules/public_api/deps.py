"""Shared route dependencies of the public API."""
from __future__ import annotations

from fastapi import Header

from app.core.errors import ValidationFailed


def idempotency_key_required(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    """Every POST on the public API needs an Idempotency-Key (1–200 chars). The same key with the same body replays
    the first answer; with another body it is 409 idempotency_payload_mismatch (app.core.idempotency)."""
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationFailed("Idempotency-Key-headeren er påkrævet på POST", code="idempotency_key_required",
                               field_errors=[{"field": "Idempotency-Key"}])
    if len(idempotency_key) > 200:
        raise ValidationFailed("Idempotency-Key må højst være 200 tegn", code="idempotency_key_required",
                               field_errors=[{"field": "Idempotency-Key"}])
    return idempotency_key.strip()
