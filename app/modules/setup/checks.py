"""Setup checks (G05).

A check result records scope, time, environment, the configuration versions it
depended on and evidence. Statuses: untested, passed, failed, stale.
Checks whose underlying capability is not implemented cannot be run; running
them returns 501 and records nothing. A simulated or server-side check can
never mark a production integration as active.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.errors import NotImplementedYet
from app.models import (
    BusinessProfile,
    CheckResult,
    GoalSelection,
    KnowledgeItem,
    KnowledgeVersion,
    LanguageSettings,
    Workspace,
    WorkspaceCategory,
)
from app.modules.integrations.registry import capability


@dataclass(frozen=True)
class CheckDefinition:
    key: str
    label: str
    depends_on: tuple[str, ...]  # configuration areas: profile, goals, languages, knowledge, integrations
    capability: str | None = None  # integration capability required to run
    scope: str = "workspace"
    description: str = ""
    required_when: tuple[str, ...] = field(default_factory=tuple)  # goal flags; empty = always


CHECKS: dict[str, CheckDefinition] = {
    c.key: c
    for c in [
        CheckDefinition("profile.completeness", "Virksomhedsprofil er komplet", ("profile",),
                        description="Navn, beskrivelse, tidszone og mindst én kategori er udfyldt."),
        CheckDefinition("languages.consistency", "Sprogindstillinger er konsistente", ("languages",),
                        description="Standardsamtalesproget er blandt de aktiverede sprog."),
        CheckDefinition("knowledge.approved_coverage", "Godkendt viden dækker minimum", ("knowledge",),
                        description="Mindst én godkendt ydelse og godkendte åbningstider findes."),
        CheckDefinition("knowledge.assistant_endpoint", "Assistentens vidensendpoint leverer kun godkendt viden",
                        ("knowledge",), description="Server-selvtest af det aktive vidensudtræk."),
        CheckDefinition("telephony.test_call", "Prøveopkald til din mobil", ("goals", "knowledge", "integrations"),
                        capability="telephony.inbound", required_when=("inbound_phone",),
                        description="Kræver en implementeret telefoniudbyder."),
        CheckDefinition("telephony.forwarding", "Viderestilling fra eksisterende nummer",
                        ("goals", "integrations"), capability="telephony.inbound", required_when=("inbound_phone",),
                        description="Kræver en implementeret telefoniudbyder."),
        CheckDefinition("calendar.connection", "Kalenderforbindelse verificeret", ("goals", "integrations"),
                        capability="calendar", required_when=("booking",),
                        description="Kræver en implementeret kalenderadapter; en simuleret test åbner ikke produktion."),
        CheckDefinition("webchat.widget", "Web-widget installeret", ("goals", "integrations"), capability="webchat",
                        required_when=("webchat",), description="Kræver widget-udrulning (etape 2)."),
        CheckDefinition("campaign.test_call", "Kampagnetest-opkald", ("goals", "knowledge", "integrations"),
                        capability="telephony.outbound", required_when=("campaigns",),
                        description="Kræver udgående telefoni (etape 4)."),
    ]
}


def _now() -> datetime:
    return datetime.now(UTC)


def config_versions(db: OrmSession, workspace_id: uuid.UUID) -> dict:
    ws = db.get(Workspace, workspace_id)
    p = db.get(BusinessProfile, workspace_id)
    g = db.get(GoalSelection, workspace_id)
    ls = db.get(LanguageSettings, workspace_id)
    return {
        "profile": p.version if p else 0,
        "goals": g.version if g else 0,
        "languages": ls.version if ls else 0,
        "knowledge": ws.knowledge_revision if ws else 0,
    }


def latest_results(db: OrmSession, workspace_id: uuid.UUID) -> dict[str, CheckResult]:
    rows = db.scalars(select(CheckResult).where(CheckResult.workspace_id == workspace_id)
                      .order_by(CheckResult.check_key, CheckResult.run_at.desc()))
    latest: dict[str, CheckResult] = {}
    for r in rows:
        latest.setdefault(r.check_key, r)
    return latest


def invalidate_checks(db: OrmSession, workspace_id: uuid.UUID, *, changed_area: str, reason: str) -> list[str]:
    """Mark the latest passed/failed result of every check that depends on the
    changed area as stale. Independent checks are untouched."""
    affected: list[str] = []
    for key, res in latest_results(db, workspace_id).items():
        d = CHECKS.get(key)
        if d is None or changed_area not in d.depends_on:
            continue
        if res.status in ("passed", "failed"):
            res.status = "stale"
            res.stale_reason = reason
            res.stale_at = _now()
            affected.append(key)
    return affected


def _evaluate(db: OrmSession, workspace_id: uuid.UUID, key: str) -> tuple[bool, dict]:
    if key == "profile.completeness":
        p = db.get(BusinessProfile, workspace_id)
        cats = db.scalars(select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == workspace_id)).all()
        missing = []
        if not p or not p.legal_name.strip():
            missing.append("legal_name")
        if not p or not p.description.strip():
            missing.append("description")
        if not p or not p.timezone:
            missing.append("timezone")
        if not cats:
            missing.append("categories")
        return not missing, {"missing_fields": missing, "category_count": len(cats)}
    if key == "languages.consistency":
        ls = db.get(LanguageSettings, workspace_id)
        ok = bool(ls) and ls.default_conversation_language in ls.enabled_conversation_languages
        return ok, {"default": ls.default_conversation_language if ls else None,
                    "enabled": ls.enabled_conversation_languages if ls else []}
    if key == "knowledge.approved_coverage":
        approved = db.execute(
            select(KnowledgeItem.kind).join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
            .where(KnowledgeItem.workspace_id == workspace_id, KnowledgeVersion.status == "approved",
                   KnowledgeItem.archived_at.is_(None))
        ).scalars().all()
        kinds = set(approved)
        missing = [k for k in ("service", "opening_hours") if k not in kinds]
        return not missing, {"approved_kinds": sorted(kinds), "missing_kinds": missing, "approved_count": len(approved)}
    if key == "knowledge.assistant_endpoint":
        from app.modules.knowledge.service import active_knowledge

        items = active_knowledge(db, workspace_id)
        leaked = [i["id"] for i in items if i["status"] != "approved"]
        return not leaked, {"active_items": len(items), "non_approved_leaked": leaked}
    raise KeyError(key)


def run_check(db: OrmSession, workspace_id: uuid.UUID, key: str, *, run_by: uuid.UUID | None,
              environment: str) -> CheckResult:
    d = CHECKS.get(key)
    if d is None:
        from app.core.errors import NotFound

        raise NotFound("Ukendt check")
    if d.capability is not None:
        cap = capability(d.capability)
        if cap.status != "available":
            raise NotImplementedYet(
                f"Checket '{d.label}' kan ikke køres: integrationen '{cap.label}' er ikke implementeret. "
                "Der registreres intet resultat.",
                extra={"capability": cap.key, "capability_status": cap.status},
            )
    ok, evidence = _evaluate(db, workspace_id, key)
    res = CheckResult(workspace_id=workspace_id, check_key=key, scope=d.scope, status="passed" if ok else "failed",
                      environment=environment, config_versions=config_versions(db, workspace_id), evidence=evidence,
                      run_by=run_by)
    db.add(res)
    db.flush()
    return res
