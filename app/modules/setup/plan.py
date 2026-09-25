"""Personal setup plan (G01–G08).

The plan is computed on the server from goals, stored configuration, knowledge
state, check results, integration capabilities and the caller's role. Nothing
in the plan is a client-writable "done" flag. Required tasks cannot be skipped;
optional tasks can. A task whose capability is not implemented in this stage is
reported as `not_available` and blocks the activation that depends on it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.auth import WorkspaceContext
from app.models import (
    ROLE_RANK,
    AuditLog,
    BusinessProfile,
    GoalSelection,
    KnowledgeItem,
    KnowledgeVersion,
    LanguageSettings,
    SetupTaskState,
    WorkspaceCategory,
)
from app.modules.integrations.registry import capability
from app.modules.setup.checks import CHECKS, latest_results


@dataclass
class Snapshot:
    ctx: WorkspaceContext
    profile: BusinessProfile
    goals: GoalSelection
    languages: LanguageSettings
    categories: int
    approved_kinds: dict[str, int]
    in_review: int
    open_drafts: int
    checks: dict
    states: dict[str, SetupTaskState]


@dataclass(frozen=True)
class TaskDef:
    key: str
    label: str
    phase: str
    explanation: str
    destination: str  # canonical frontend route (requirement matrix), never a SCREEN_* number
    requirement_ids: tuple[str, ...]
    required: Callable[[Snapshot], bool | None]  # True required, False optional, None not applicable
    complete: Callable[[Snapshot], bool]
    depends_on: tuple[str, ...] = ()
    capability: str | None = None
    min_role: str = "staff"
    started: Callable[[Snapshot], bool] | None = None
    estimated_minutes: int = 5


def _reception(s: Snapshot) -> bool:
    return s.goals.product_intent in ("reception", "both")


def _campaigns(s: Snapshot) -> bool:
    return s.goals.product_intent in ("campaigns", "both")


TASKS: list[TaskDef] = [
    TaskDef("business.profile", "Udfyld virksomhedsoplysninger", "Din virksomhed",
            "Navn, beskrivelse og tidszone bruges i alle samtaler og rapporter. Manuel opsætning uden hjemmeside er fuldt understøttet.",
            "/onboarding/business", ("O01", "S01"), lambda s: True,
            lambda s: bool(s.profile.legal_name.strip() and s.profile.description.strip() and s.profile.timezone),
            started=lambda s: s.profile.version > 1, estimated_minutes=5),
    TaskDef("business.categories", "Vælg branchekategorier", "Din virksomhed",
            "Mindst én kategori (gerne flere eller din egen) giver assistenten den rette kontekst.",
            "/onboarding/business#categories", ("O01",), lambda s: True, lambda s: s.categories > 0, estimated_minutes=2),
    TaskDef("goals.select", "Bekræft produktmål og kapabiliteter", "Mål og sprog",
            "Reception, kampagner eller begge. Callback hører under reception; booking er valgfri.",
            "/onboarding/goals", ("O03", "G02"), lambda s: True, lambda s: s.goals.version > 1, estimated_minutes=3),
    TaskDef("languages.settings", "Fastlæg sprog", "Mål og sprog",
            "Brugerflade-, standardsamtale-, aktiverede samtale- og rapportsprog gemmes hver for sig.",
            "/onboarding/languages", ("O04",), lambda s: True, lambda s: s.languages.version > 1, estimated_minutes=2),
    TaskDef("knowledge.services", "Beskriv dine ydelser", "Viden og svar",
            "Mindst én godkendt ydelse er nødvendig, før assistenten kan svare kunder.",
            "/app/knowledge/catalogue", ("K03", "O02"), lambda s: True,
            lambda s: s.approved_kinds.get("service", 0) > 0, depends_on=("business.profile",),
            started=lambda s: s.open_drafts > 0 or s.in_review > 0, estimated_minutes=10),
    TaskDef("knowledge.opening_hours", "Angiv åbningstider", "Viden og svar",
            "Godkendte åbningstider styrer, hvad assistenten lover om tilgængelighed.",
            "/app/knowledge", ("K01", "O02"), lambda s: True if _reception(s) else False,
            lambda s: s.approved_kinds.get("opening_hours", 0) > 0, depends_on=("business.profile",), estimated_minutes=3),
    TaskDef("knowledge.coverage_area", "Angiv dækningsområde", "Viden og svar",
            "Valgfrit: hvilke områder betjener I?", "/app/knowledge/catalogue", ("K03",), lambda s: False,
            lambda s: s.approved_kinds.get("coverage_area", 0) > 0, estimated_minutes=3),
    TaskDef("knowledge.answers", "Kendte og ukendte svar", "Viden og svar",
            "Valgfrit: faste svar og emner assistenten ikke må udtale sig om.", "/app/knowledge", ("K01", "K05"),
            lambda s: False,
            lambda s: s.approved_kinds.get("known_answer", 0) + s.approved_kinds.get("unknown_answer", 0) > 0,
            estimated_minutes=5),
    TaskDef("knowledge.review", "Godkend viden til gennemgang", "Viden og svar",
            "Kladder skal godkendes af en administrator eller ejer, før de bliver aktiv viden.",
            "/app/knowledge/review", ("K05",), lambda s: (s.in_review > 0 or s.open_drafts > 0),
            lambda s: s.in_review == 0 and s.open_drafts == 0, min_role="admin",
            started=lambda s: s.in_review > 0, estimated_minutes=5),
    TaskDef("checks.server", "Kør konfigurationstjek", "Test og godkendelse",
            "Serveren kontrollerer profil, sprog og godkendt viden. Tjek bliver forældede, når konfigurationen ændres.",
            "/app/setup/readiness", ("G05",), lambda s: True,
            lambda s: all(s.checks.get(k) is not None and s.checks[k].status == "passed"
                          for k in ("profile.completeness", "languages.consistency", "knowledge.approved_coverage",
                                    "knowledge.assistant_endpoint")),
            depends_on=("business.profile", "business.categories", "languages.settings", "knowledge.services"),
            started=lambda s: any(k in s.checks for k in CHECKS), estimated_minutes=1),
    TaskDef("reception.telephony_forwarding", "Viderestil dit telefonnummer", "Kanaler",
            "Instruktioner til omstilling fra dit teleselskab. Kræver en implementeret telefoniudbyder.",
            "/app/settings/integrations", ("S03", "O07"), lambda s: True if (_reception(s) and s.goals.inbound_phone) else None,
            lambda s: False, capability="telephony.inbound", depends_on=("knowledge.services",), estimated_minutes=10),
    TaskDef("reception.test_call", "Gennemfør prøveopkald", "Test og godkendelse",
            "Et reelt prøveopkald til din mobil. Kræver telefoniudbyder; et simuleret opkald tæller ikke.",
            "/onboarding/test", ("O06",), lambda s: True if (_reception(s) and s.goals.inbound_phone) else None,
            lambda s: s.checks.get("telephony.test_call") is not None and s.checks["telephony.test_call"].status == "passed",
            capability="telephony.inbound", depends_on=("checks.server", "reception.telephony_forwarding"),
            estimated_minutes=5),
    TaskDef("reception.webchat", "Installér web-widget", "Kanaler",
            "Slå widgetten til, angiv jeres domæner og indsæt koden på hjemmesiden. Tjekket består, når chatten er åbnet dér.",
            "/app/settings/webchat", ("W01", "O07"), lambda s: True if (_reception(s) and s.goals.webchat) else None,
            lambda s: s.checks.get("webchat.widget") is not None and s.checks["webchat.widget"].status == "passed",
            capability="webchat", estimated_minutes=10),
    TaskDef("booking.calendar", "Forbind kalender", "Kanaler",
            "Kalenderadapteren er ikke implementeret endnu; en simuleret forbindelse aktiverer ikke booking.",
            "/app/settings/integrations", ("BK06", "O07"), lambda s: True if s.goals.booking else None,
            lambda s: s.checks.get("calendar.connection") is not None and s.checks["calendar.connection"].status == "passed",
            capability="calendar", estimated_minutes=10),
    TaskDef("campaign.first", "Opret din første kampagne", "Kampagner",
            "Kampagneoprettelse, manuskript og betaling kommer i etape 4. Betaling starter aldrig opkald.",
            "/app/campaigns/new", ("C01", "O07"), lambda s: True if _campaigns(s) else None, lambda s: False,
            capability="telephony.outbound", depends_on=("knowledge.services", "checks.server"), estimated_minutes=15),
    TaskDef("activation.reception", "Aktivér reception", "Aktivering",
            "Særskilt handling. Kræver bestået prøveopkald og en implementeret telefoniudbyder.",
            "/app/setup/launch", ("G06", "O07"), lambda s: True if _reception(s) else None, lambda s: False,
            capability="telephony.inbound", min_role="admin",
            depends_on=("checks.server", "reception.test_call"), estimated_minutes=1),
    TaskDef("activation.campaigns", "Aktivér kampagner", "Aktivering",
            "Særskilt handling; adskilt fra betaling og lancering.", "/app/setup/launch", ("G06",),
            lambda s: True if _campaigns(s) else None, lambda s: False, capability="telephony.outbound",
            min_role="admin", depends_on=("campaign.first",), estimated_minutes=1),
]
TASK_INDEX = {t.key: t for t in TASKS}


def snapshot(db: OrmSession, ctx: WorkspaceContext) -> Snapshot:
    ws_id = ctx.workspace.id
    approved_rows = db.execute(
        select(KnowledgeItem.kind, func.count()).join(KnowledgeVersion, KnowledgeVersion.item_id == KnowledgeItem.id)
        .where(KnowledgeItem.workspace_id == ws_id, KnowledgeVersion.status == "approved",
               KnowledgeItem.archived_at.is_(None)).group_by(KnowledgeItem.kind)
    ).all()
    in_review = db.scalar(select(func.count()).select_from(KnowledgeVersion)
                          .where(KnowledgeVersion.workspace_id == ws_id, KnowledgeVersion.status == "in_review")) or 0
    open_drafts = db.scalar(select(func.count()).select_from(KnowledgeVersion)
                            .where(KnowledgeVersion.workspace_id == ws_id, KnowledgeVersion.status == "draft")) or 0
    states = {s.task_key: s for s in db.scalars(select(SetupTaskState).where(SetupTaskState.workspace_id == ws_id))}
    return Snapshot(
        ctx=ctx, profile=db.get(BusinessProfile, ws_id), goals=db.get(GoalSelection, ws_id),
        languages=db.get(LanguageSettings, ws_id),
        categories=db.scalar(select(func.count()).select_from(WorkspaceCategory)
                             .where(WorkspaceCategory.workspace_id == ws_id)) or 0,
        approved_kinds={k: n for k, n in approved_rows}, in_review=in_review, open_drafts=open_drafts,
        checks=latest_results(db, ws_id), states=states,
    )


def compute_plan(db: OrmSession, ctx: WorkspaceContext) -> dict:
    s = snapshot(db, ctx)
    tasks: list[dict] = []
    status_by_key: dict[str, str] = {}
    for t in TASKS:
        req = t.required(s)
        if req is None:
            continue  # not applicable for the selected goals
        state = s.states.get(t.key)
        complete = t.complete(s)
        blocked_by: list[dict] = []
        cap_status = None
        if t.capability:
            cap = capability(t.capability)
            cap_status = cap.status
            if cap.status != "available":
                blocked_by.append({"type": "capability", "capability": cap.key, "status": cap.status,
                                   "message": f"{cap.label}: ikke implementeret i denne etape. {cap.note}"})
        for dep in t.depends_on:
            dep_status = status_by_key.get(dep)
            if dep_status is not None and dep_status not in ("complete", "skipped"):
                blocked_by.append({"type": "dependency", "task_key": dep,
                                   "message": f"Kræver først: {TASK_INDEX[dep].label}"})
        if ROLE_RANK[ctx.role] < ROLE_RANK[t.min_role]:
            blocked_by.append({"type": "permission", "required_role": t.min_role,
                               "message": f"Kræver rollen {t.min_role} eller højere. Bed en kollega med rettigheden."})
        if complete:
            status = "complete"
        elif state is not None and state.skipped_at is not None and not req:
            status = "skipped"
        elif cap_status is not None and cap_status != "available":
            status = "not_available"
        elif blocked_by:
            status = "blocked"
        elif t.started and t.started(s):
            status = "in_progress"
        else:
            status = "not_started"
        status_by_key[t.key] = status
        stale = [k for k in CHECKS if k in s.checks and s.checks[k].status == "stale" and
                 (t.key == "checks.server" and k in ("profile.completeness", "languages.consistency",
                                                    "knowledge.approved_coverage", "knowledge.assistant_endpoint"))]
        if stale and status == "complete":
            status = "in_progress"
            status_by_key[t.key] = status
        tasks.append({
            "key": t.key, "label": t.label, "phase": t.phase, "explanation": t.explanation,
            "destination": t.destination, "requirement_ids": list(t.requirement_ids), "required": bool(req),
            "status": status, "blocked_by": blocked_by, "can_skip": (not req) and status not in ("complete",),
            "min_role": t.min_role, "you_can_act": ROLE_RANK[ctx.role] >= ROLE_RANK[t.min_role],
            "assigned_to": str(state.assigned_to) if state and state.assigned_to else None,
            "estimated_minutes": t.estimated_minutes, "stale_checks": stale,
            "capability_status": cap_status,
        })

    required = [t for t in tasks if t["required"]]
    req_done = [t for t in required if t["status"] == "complete"]
    next_action = None
    for t in tasks:
        if t["required"] and t["status"] in ("not_started", "in_progress") and t["you_can_act"]:
            next_action = t
            break
    if next_action is None:
        for t in tasks:
            if not t["required"] and t["status"] in ("not_started", "in_progress") and t["you_can_act"]:
                next_action = t
                break
    remaining_blocked = [t for t in tasks if t["required"] and t["status"] in ("blocked", "not_available")]
    explanation = None
    if remaining_blocked:
        prefix = "Alle resterende nødvendige trin er blokeret: " if next_action is None else "Blokerede nødvendige trin: "
        explanation = prefix + "; ".join(f"{t['label']} ({t['blocked_by'][0]['message']})" for t in remaining_blocked)
    elif next_action is None:
        explanation = "Alle trin i denne etape er gennemført."

    last_activity = db.scalar(select(AuditLog).where(AuditLog.workspace_id == ctx.workspace.id)
                              .order_by(AuditLog.created_at.desc()).limit(1))
    return {
        "workspace_id": str(ctx.workspace.id), "role": ctx.role, "guidance_mode": s.goals.guidance_mode,
        "product_intent": s.goals.product_intent,
        "progress": {"required_total": len(required), "required_complete": len(req_done),
                     "percent": int(round(100 * len(req_done) / len(required))) if required else 0,
                     "optional_total": len(tasks) - len(required),
                     "estimated_minutes_remaining": sum(t["estimated_minutes"] for t in required
                                                        if t["status"] != "complete")},
        "next_action": next_action, "next_action_explanation": explanation,
        "blocked_required": [t["key"] for t in remaining_blocked],
        "resume": {"open_drafts": s.open_drafts, "in_review": s.in_review,
                   "last_activity_at": last_activity.created_at.isoformat() if last_activity else None,
                   "last_action": last_activity.action if last_activity else None},
        "tasks": tasks,
        "checks": [
            {"key": k, "label": d.label, "description": d.description, "depends_on": list(d.depends_on),
             "capability": d.capability, "runnable": d.capability is None or capability(d.capability).status == "available",
             "status": s.checks[k].status if k in s.checks else "untested",
             "last_run_at": s.checks[k].run_at.isoformat() if k in s.checks else None,
             "environment": s.checks[k].environment if k in s.checks else None,
             "config_versions": s.checks[k].config_versions if k in s.checks else None,
             "evidence": s.checks[k].evidence if k in s.checks else None,
             "stale_reason": s.checks[k].stale_reason if k in s.checks else None}
            for k, d in CHECKS.items()
            if not d.required_when or any(
                (f == "campaigns" and _campaigns(s)) or (f != "campaigns" and getattr(s.goals, f, False))
                for f in d.required_when)
        ],
        "computed_at": datetime.now().astimezone().isoformat(),
    }
