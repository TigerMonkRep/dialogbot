"""Shared pieces of the internal sales channel: the mode gate, the industry list and the status page."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError
from app.models import SalesIndustry
from app.modules.sales import script

MODES = ("off", "research", "simulation", "test", "live")
RESEARCH_MODES = ("research", "simulation", "test", "live")
SIMULATION_MODES = ("simulation", "test", "live")


class ChannelOff(ApiError):
    status_code = 501
    code = "sales_channel_off"


def mode() -> str:
    return get_settings().sales_outbound_mode


def require(modes: tuple[str, ...] = RESEARCH_MODES) -> None:
    m = mode()
    if m == "off":
        raise ChannelOff("Salgskanalen er slået fra (SALES_OUTBOUND_MODE=off).")
    if m not in modes:
        raise ChannelOff(f"Kræver SALES_OUTBOUND_MODE={' eller '.join(modes)} (nu: {m}).",
                         code="sales_mode_not_allowed")


def industries(db: OrmSession, *, include_inactive: bool = False) -> dict[str, dict]:
    """Code industries (sales/script.INDUSTRIES) merged with the operator's own rows, which win per key."""
    out: dict[str, dict] = {k: {"key": k, "label": v["label"], "google_types": list(v.get("google_types", [])),
                                "search_terms": list(v.get("search_terms", [])), "active": True, "source": "code"}
                            for k, v in script.INDUSTRIES.items()}
    for row in db.scalars(select(SalesIndustry)):
        out[row.key] = {"key": row.key, "label": row.label, "google_types": list(row.google_types),
                        "search_terms": list(row.search_terms), "active": row.active, "source": "admin"}
    return {k: v for k, v in out.items() if include_inactive or v["active"]}


def industry_for_types(db: OrmSession, types: list[str]) -> str | None:
    for key, ind in industries(db).items():
        if set(types) & set(ind["google_types"]):
            return key
    return None


def status(db: OrmSession) -> dict:
    """What works and what is missing. Names of settings only, never values."""
    from app.modules.business import cvr
    from app.modules.sales import service

    s = get_settings()
    ws = service.sales_workspace(db)
    missing = []
    if s.sales_outbound_mode == "off":
        missing.append("SALES_OUTBOUND_MODE er off – sæt research eller simulation for at bruge salgskanalen.")
    if not s.google_places_api_key:
        missing.append("GOOGLE_PLACES_API_KEY er ikke sat – søgningen kører på demo-data.")
    if not cvr.configured():
        missing.append("CVR_USERNAME/CVR_PASSWORD er ikke sat – reklamebeskyttelse vises som ukendt.")
    if ws is None:
        missing.append("SALES_WORKSPACE_ID er ikke sat – research (AI-udtræk) og simulation kræver salgsarbejdsrummet.")
    if s.sales_outbound_mode in ("test", "live") and not (s.vapi_api_key and s.vapi_server_secret):
        missing.append("VAPI_API_KEY/VAPI_SERVER_SECRET mangler – der kan ikke ringes op.")
    if s.sales_outbound_mode == "test" and not s.sales_test_numbers.strip():
        missing.append("SALES_TEST_NUMBERS er tom – testopkald kræver mindst ét testnummer.")
    if s.sales_outbound_mode in ("off", "research", "simulation"):
        missing.append("Opkald kræver SALES_OUTBOUND_MODE=test (kun testnumre) eller live.")
    if s.ai_provider == "none":
        missing.append("AI_PROVIDER=none – research og simulation kræver en AI-udbyder.")
    return {"mode": s.sales_outbound_mode,
            "places": "google" if s.google_places_api_key else "demo",
            "cvr_configured": cvr.configured(),
            "sales_workspace": {"id": str(ws.id), "name": ws.name} if ws else None,
            "ai_provider": s.ai_provider,
            "test_numbers": len([n for n in s.sales_test_numbers.split(",") if n.strip()]),
            "limits": {"search_max_results": s.sales_search_max_results,
                       "search_daily_request_cap": s.sales_search_daily_request_cap,
                       "research_max_pages": s.sales_research_max_pages,
                       "google_cache_days": s.google_places_cache_days},
            "phases": {"research": True, "simulation": True, "campaigns": True, "test_calls": True,
                       "offers": False, "recordings": False},
            "missing": missing}
