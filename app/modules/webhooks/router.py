from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.db import get_db
from app.modules.webhooks import resend

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/resend")
async def resend_webhook(request: Request, db: OrmSession = Depends(get_db)):
    """Resend delivery events. Public, but every request must carry a valid Svix signature."""
    secret = get_settings().resend_webhook_secret
    if not secret:
        raise resend.WebhookNotConfigured("Resend-webhook er ikke konfigureret (RESEND_WEBHOOK_SECRET mangler)")
    body = await request.body()
    h = request.headers
    msg_id = h.get("svix-id")
    resend.verify_signature(secret, msg_id, h.get("svix-timestamp"), h.get("svix-signature"), body)
    try:
        payload = json.loads(body)
    except ValueError as e:
        raise ValidationFailed("Ugyldig JSON") from e
    if not isinstance(payload, dict):
        raise ValidationFailed("Ugyldig hændelse")
    result = resend.process_event(db, msg_id, payload)
    db.commit()
    return {"received": True, **result}
