from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import get_scoped
from app.core.errors import Conflict, ValidationFailed
from app.core.idempotency import IdempotencyGuard
from app.db import get_db
from app.models import WebhookEndpoint
from app.modules.public_api import webhook_delivery as wd
from app.modules.public_api.auth import PublicPrincipal, require_scope
from app.modules.public_api.deps import idempotency_key_required
from app.modules.public_api.schemas import v1

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["webhooks"])

MAX_ENDPOINTS = 10


def _validate_events(events: list[str]) -> list[str]:
    unknown = sorted({e for e in events if e not in wd.EVENTS})
    if unknown:
        raise ValidationFailed("Ukendt hændelsestype: " + ", ".join(unknown), field_errors=[{"field": "events"}],
                               extra={"known_events": list(wd.EVENTS)})
    return [e for e in wd.EVENTS if e in set(events)]


@router.get("/webhooks/events", summary="Hændelsestyper, der kan abonneres på")
def list_events(principal: PublicPrincipal = Depends(require_scope("webhooks:manage"))):
    return {"items": [{"type": k, "description": v} for k, v in wd.EVENTS.items()]}


@router.get("/webhooks", response_model=v1.Page[v1.WebhookEndpoint], summary="Webhook-endpoints")
def list_webhooks(principal: PublicPrincipal = Depends(require_scope("webhooks:manage")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == principal.workspace_id)
                      .order_by(WebhookEndpoint.created_at, WebhookEndpoint.id)).all()
    return {"items": [v1.webhook_out(w) for w in rows], "next_cursor": None}


@router.post("/webhooks", status_code=status.HTTP_201_CREATED, response_model=v1.WebhookEndpointCreated,
             summary="Opret et webhook-endpoint (hemmeligheden vises kun i dette svar)")
def create_webhook(body: v1.WebhookEndpointIn, request: Request, response: Response,
                   idem: str = Depends(idempotency_key_required),
                   principal: PublicPrincipal = Depends(require_scope("webhooks:manage")), db: OrmSession = Depends(get_db)):
    from app.modules.integrations.connectors.webhook import url_allowed

    guard = IdempotencyGuard(db, f"{principal.idempotency_scope}:webhooks.create", idem, body.model_dump())
    if guard.replay:
        st, replay = guard.replay  # stored without the secret: a replay never hands it out again
        response.status_code = st
        return {**replay, "secret": ""}
    events = _validate_events(body.events)
    if not url_allowed(body.url):
        raise ValidationFailed("Adressen skal være en offentlig https-adresse på standardporten",
                               code="url_not_allowed", field_errors=[{"field": "url"}])
    ws_id = principal.workspace_id
    count = db.scalar(select(func.count()).select_from(WebhookEndpoint).where(WebhookEndpoint.workspace_id == ws_id)) or 0
    if count >= MAX_ENDPOINTS:
        raise Conflict(f"Højst {MAX_ENDPOINTS} webhook-endpoints pr. arbejdsrum", code="webhook_limit")
    secret = wd.new_secret()
    w = WebhookEndpoint(workspace_id=ws_id, url=body.url.strip(), description=body.description.strip(), events=events,
                        created_by_key_id=principal.key.id)
    db.add(w)
    db.flush()
    wd.put_secret(w, secret)
    db.flush()
    record_audit(db, workspace_id=ws_id, actor_user_id=None, action="webhook_endpoint.created", object_type="webhook_endpoint",
                 object_id=w.id, after={"url": w.url, "events": events, "api_key_id": str(principal.key.id)},
                 request_id=getattr(request.state, "request_id", None))
    view = v1.webhook_out(w).model_dump(mode="json")
    guard.store(201, view)
    db.commit()
    return {**view, "secret": secret}


@router.get("/webhooks/{endpoint_id}", response_model=v1.WebhookEndpoint, summary="Ét webhook-endpoint")
def get_webhook(endpoint_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("webhooks:manage")),
                db: OrmSession = Depends(get_db)) -> v1.WebhookEndpoint:
    return v1.webhook_out(get_scoped(db, WebhookEndpoint, endpoint_id, principal.workspace_id))


@router.patch("/webhooks/{endpoint_id}", response_model=v1.WebhookEndpoint,
              summary="Ret hændelser/beskrivelse, eller genaktivér et endpoint der blev slået fra")
def patch_webhook(endpoint_id: uuid.UUID, body: v1.WebhookEndpointPatch, request: Request,
                  principal: PublicPrincipal = Depends(require_scope("webhooks:manage")), db: OrmSession = Depends(get_db)):
    w = get_scoped(db, WebhookEndpoint, endpoint_id, principal.workspace_id)
    before = {"events": list(w.events or []), "active": w.active}
    if body.events is not None:
        w.events = _validate_events(body.events)
    if body.description is not None:
        w.description = body.description.strip()
    if body.active is not None:
        w.active = body.active
        if body.active:
            w.failure_count, w.disabled_at, w.disabled_reason = 0, None, None
        else:
            w.disabled_at, w.disabled_reason = datetime.now(UTC), "Slået fra via API"
    record_audit(db, workspace_id=w.workspace_id, actor_user_id=None, action="webhook_endpoint.updated",
                 object_type="webhook_endpoint", object_id=w.id, before=before,
                 after={"events": list(w.events or []), "active": w.active, "api_key_id": str(principal.key.id)},
                 request_id=getattr(request.state, "request_id", None))
    db.commit()
    return v1.webhook_out(w)


@router.delete("/webhooks/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Slet et webhook-endpoint")
def delete_webhook(endpoint_id: uuid.UUID, request: Request,
                   principal: PublicPrincipal = Depends(require_scope("webhooks:manage")), db: OrmSession = Depends(get_db)):
    w = get_scoped(db, WebhookEndpoint, endpoint_id, principal.workspace_id)
    record_audit(db, workspace_id=w.workspace_id, actor_user_id=None, action="webhook_endpoint.deleted",
                 object_type="webhook_endpoint", object_id=w.id, before={"url": w.url, "api_key_id": str(principal.key.id)},
                 request_id=getattr(request.state, "request_id", None))
    db.delete(w)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/webhooks/{endpoint_id}/deliveries", response_model=v1.Page[v1.WebhookDelivery],
            summary="De seneste leveringer (fra outboxen), nyeste først")
def list_deliveries(endpoint_id: uuid.UUID, principal: PublicPrincipal = Depends(require_scope("webhooks:manage")),
                    db: OrmSession = Depends(get_db)):
    w = get_scoped(db, WebhookEndpoint, endpoint_id, principal.workspace_id)
    items = [v1.WebhookDelivery(id=ev.id, event_id=ev.payload.get("event_id", ""), type=ev.payload.get("type", ""),
                                status=ev.status, attempts=ev.attempts, max_attempts=ev.max_attempts,
                                next_attempt_at=ev.next_attempt_at if ev.status == "queued" else None,
                                last_error=ev.last_error, created_at=ev.created_at, processed_at=ev.processed_at)
             for ev in wd.deliveries(db, w.id)]
    return {"items": items, "next_cursor": None}
