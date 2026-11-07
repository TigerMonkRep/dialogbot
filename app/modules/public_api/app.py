"""The public API as its own FastAPI application, mounted at /v1 by app.main.create_app (APP_SURFACE public|all).

Its own OpenAPI document (`/v1/openapi.json`, title "Dialogbot Public API", version 1.0.0 – exported to
docs/public-openapi.json by scripts/export_public_openapi.py) and docs (`/v1/docs`), the same error envelope as the
internal API, and the per-key rate limit middleware. Being a mounted sub-application keeps it out of the internal
API's OpenAPI document and lets APP_SURFACE=public serve only this.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.core.errors import install_error_handlers
from app.modules.public_api.ratelimit import RateLimitMiddleware
from app.modules.public_api.routers import (
    bookings,
    calls,
    campaigns,
    conversations,
    knowledge,
    leads,
    me,
    reports,
    webhooks,
)

VERSION = "1.0.0"

DESCRIPTION = """Dialogbot Public API v1 – læs opkald, aftaler, henvendelser, samtaler, den godkendte viden og
kampagner for ét arbejdsrum, og modtag hændelser som signerede webhooks.

* **Auth:** `Authorization: Bearer dbk_live_…` (API-nøgle fra Integrationer → API-nøgler i appen).
* **Scopes:** hver rute kræver ét scope; 403 `insufficient_scope` siger hvilket.
* **Pagination:** `?limit=&cursor=`; svaret har `next_cursor` (null = sidste side).
* **Skrivninger:** `Idempotency-Key` er påkrævet på POST. Ingen rute i v1 godkender eller sætter en status –
  godkendelse sker altid i appen.
* **Rate limit:** 600 læsninger og 60 skrivninger pr. minut pr. nøgle; 429 med `Retry-After`.

Fuld dokumentation: docs/public-api.md i repoet (developers.dialogbot.app).
"""


def create_public_app() -> FastAPI:
    from app.config import get_settings

    app = FastAPI(title="Dialogbot Public API", version=VERSION, description=DESCRIPTION, openapi_url="/openapi.json",
                  docs_url="/docs", redoc_url=None,
                  servers=[{"url": get_settings().public_api_base_url.rstrip("/") + "/v1", "description": "Produktion"}])
    app.add_middleware(RateLimitMiddleware)
    install_error_handlers(app)
    for r in (me.router, calls.router, conversations.router, bookings.router, leads.router, knowledge.router,
              campaigns.router, reports.router, webhooks.router):
        app.include_router(r)
    return app
