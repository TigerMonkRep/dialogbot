from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import RequestIdMiddleware, configure_logging
from app.modules.ai.router import router as ai_router
from app.modules.billing.router import router as billing_router
from app.modules.bookings.router import public_router as bookings_public_router
from app.modules.bookings.router import router as bookings_router
from app.modules.business.router import router as business_router
from app.modules.campaigns.router import router as campaigns_router
from app.modules.health.router import router as health_router
from app.modules.identity.router import router as identity_router
from app.modules.integrations.router import router as integrations_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.leads.router import router as leads_router
from app.modules.overview.router import router as overview_router
from app.modules.reception.router import router as reception_router
from app.modules.reports.router import router as reports_router
from app.modules.setup.router import router as setup_router
from app.modules.telephony.router import router as telephony_router
from app.modules.telephony.router import webhook_router as vapi_webhook_router
from app.modules.waitlist.router import router as waitlist_router
from app.modules.webchat.public import router as webchat_public_router
from app.modules.webchat.router import router as webchat_router
from app.modules.webhooks.router import router as webhooks_router
from app.modules.workspaces.router import router as workspaces_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Dialogbot API",
        version="0.1.0",
        description=(
            "Etape 1: identitet, arbejdsrum, rettigheder, virksomhedsprofil, manuel viden med godkendelse "
            "og personlig opsætningsplan. Reception, booking, kampagner og afregning er ikke implementeret."
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health_router)
    for r in (identity_router, workspaces_router, business_router, knowledge_router, setup_router, integrations_router,
              webhooks_router, ai_router, waitlist_router,
              webchat_router, webchat_public_router, leads_router,
              reports_router, telephony_router, vapi_webhook_router, billing_router, reception_router, overview_router,
              bookings_router, bookings_public_router, campaigns_router):
        app.include_router(r, prefix=API_PREFIX)
    if settings.dev_tools_enabled:
        from app.modules.devtools.router import router as dev_router

        app.include_router(dev_router, prefix=API_PREFIX)
    return app


app = create_app()
