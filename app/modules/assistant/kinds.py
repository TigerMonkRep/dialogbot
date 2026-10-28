"""The changes the assistant «Ændr noget» can make, one entry per kind.

A kind knows three things: how to **validate** what the model proposed (the model only suggests – this is the
authoritative check), how to **describe** the change as before → after in the customer's words, and how to **apply** it
through the same service functions the forms use (so roles, versions, audit and "checks go stale" behave the same).
Nothing here is called without the person's «Godkend»; `describe` never writes."""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.audit import record_audit
from app.core.auth import WorkspaceContext
from app.core.errors import Conflict, ValidationFailed
from app.models import KnowledgeItem, KnowledgeVersion
from app.modules.bookings import service as bookings
from app.modules.knowledge import service as knowledge
from app.modules.reports import service as reports

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_DA = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
UNITS = {"m2": "pr. m²", "hour": "pr. time", "item": "pr. stk.", "job": "pr. opgave"}


def hours_text(weekly: list[dict] | None) -> str:
    """[{days, open, close}] → «Man–fre 07–16; lør 09–12»."""
    out = []
    for r in weekly or []:
        idx = sorted(DAYS.index(d) for d in r.get("days", []) if d in DAYS)
        if not idx:
            continue
        run = len(idx) > 2 and all(b == a + 1 for a, b in zip(idx, idx[1:], strict=False))
        days = f"{DAY_DA[idx[0]]}–{DAY_DA[idx[-1]]}" if run else " og ".join(DAY_DA[i] for i in idx)
        short = lambda t: t[:2] if t.endswith(":00") else t  # noqa: E731
        out.append(f"{days[0].upper()}{days[1:]} {short(r['open'])}–{short(r['close'])}")
    return "; ".join(out)


def kr(minor: int) -> str:
    return f"{minor // 100:,}".replace(",", ".") + f",{minor % 100:02d} kr. ekskl. moms"


def _current(db: OrmSession, ws_id: uuid.UUID, kind: str, title: str | None = None):
    """The item of this kind (and key, if a title is given) with its approved version and open draft."""
    q = select(KnowledgeItem).where(KnowledgeItem.workspace_id == ws_id, KnowledgeItem.kind == kind,
                                    KnowledgeItem.archived_at.is_(None))
    if title is not None:
        q = q.where(KnowledgeItem.key == knowledge._key(kind, title))
    item = db.scalars(q.order_by(KnowledgeItem.created_at)).first()
    if item is None:
        return None, None, None
    return item, knowledge.approved_version(db, item.id), knowledge.open_draft(db, item.id)


def _publish(db: OrmSession, ctx: WorkspaceContext, kind: str, title: str, content: dict, request_id: str | None) -> KnowledgeVersion:
    """Create or update the item and approve it – the person said «Godkend», so the change is live afterwards."""
    item, approved, draft = _current(db, ctx.workspace.id, kind, title if kind != "opening_hours" else None)
    if item is None:
        item, v = knowledge.create_item(db, ctx, kind=kind, title=title, content=content, source_ref="assistent", request_id=request_id)
    elif draft is not None:
        v = knowledge.edit_draft(db, ctx, draft.id, expected_edit_version=draft.edit_version, title=title, content=content,
                                 source_ref="assistent", request_id=request_id)
    else:
        v = knowledge.new_draft(db, ctx, item.id, title=title, content=content, source_ref="assistent", request_id=request_id)
    return knowledge.approve(db, ctx, v.id, request_id)


# --- validation helpers -------------------------------------------------------------------------------------------------

def _bad(msg: str) -> ValidationFailed:
    return ValidationFailed(msg, code="assistant_bad_proposal")


def _int(v: Any, lo: int, hi: int, name: str) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise _bad(f"{name} skal være et tal") from None
    if not lo <= n <= hi:
        raise _bad(f"{name} skal være mellem {lo} og {hi}")
    return n


def _text(v: Any, n: int, name: str) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    if not s:
        raise _bad(f"{name} mangler")
    return s[:n]


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    needs: str                                  # the capability the change itself needs
    help: str                                   # what the model is told about it
    validate: Callable[[dict], dict]
    describe: Callable[[OrmSession, WorkspaceContext, dict], tuple[str, str, str]]   # summary, before, after
    apply: Callable[[OrmSession, WorkspaceContext, dict, str | None], str]            # returns where to see it
    href: str = "/app/viden"


# --- opening hours ------------------------------------------------------------------------------------------------------

def _v_hours(p: dict) -> dict:
    rows = []
    for r in (p.get("weekly") or [])[:7]:
        days = [d for d in (r.get("days") or []) if d in DAYS]
        o, c = str(r.get("open") or ""), str(r.get("close") or "")
        if not days or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", o) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d|24:00", c) or o >= c:
            raise _bad("Åbningstiderne kunne ikke læses som dage og klokkeslæt")
        rows.append({"days": days, "open": o, "close": c})
    if not rows:
        raise _bad("Åbningstiderne mangler")
    return {"weekly": rows}


def _d_hours(db, ctx, p):
    _, approved, draft = _current(db, ctx.workspace.id, "opening_hours")
    cur = hours_text(((approved or draft).content if (approved or draft) else {}).get("weekly")) or "Ikke angivet"
    new = hours_text(p["weekly"])
    return f"Åbningstider: {new}", cur, new


def _a_hours(db, ctx, p, rid):
    _publish(db, ctx, "opening_hours", "Åbningstider", {"weekly": p["weekly"]}, rid)
    return "Åbningstiderne er ændret."


# --- service price ------------------------------------------------------------------------------------------------------

def _v_price(p: dict) -> dict:
    out = {"title": _text(p.get("title"), 200, "Ydelsen"), "price_net_minor": _int(p.get("price_net_minor"), 0, 100_000_000, "Prisen")}
    unit = p.get("unit")
    out["unit"] = unit if unit in UNITS else None
    return out


def _d_price(db, ctx, p):
    _, approved, draft = _current(db, ctx.workspace.id, "service", p["title"])
    cur_c = (approved or draft).content if (approved or draft) else None
    unit = p["unit"] or (cur_c or {}).get("unit")
    suffix = f" {UNITS[unit]}" if unit in UNITS else ""
    before = (f"{kr(cur_c['price_net_minor'])}{suffix}" if cur_c and isinstance(cur_c.get("price_net_minor"), int)
              else "Ingen pris" if cur_c else "Ydelsen findes ikke endnu")
    return f"{p['title']}: {kr(p['price_net_minor'])}{suffix}", before, f"{kr(p['price_net_minor'])}{suffix}"


def _a_price(db, ctx, p, rid):
    _, approved, draft = _current(db, ctx.workspace.id, "service", p["title"])
    content = dict((approved or draft).content) if (approved or draft) else {}
    content["price_net_minor"] = p["price_net_minor"]
    if p["unit"]:
        content["unit"] = p["unit"]
    _publish(db, ctx, "service", p["title"], content, rid)
    return f"Prisen på {p['title']} er ændret."


# --- known answer (Q&A) -------------------------------------------------------------------------------------------------

def _v_answer(p: dict) -> dict:
    return {"question": _text(p.get("question"), 200, "Spørgsmålet"), "answer": _text(p.get("answer"), 1500, "Svaret")}


def _d_answer(db, ctx, p):
    _, approved, draft = _current(db, ctx.workspace.id, "known_answer", p["question"])
    cur = ((approved or draft).content or {}).get("answer") if (approved or draft) else None
    return f"Fast svar: {p['question']}", cur or "Intet fast svar på det endnu", p["answer"]


def _a_answer(db, ctx, p, rid):
    _publish(db, ctx, "known_answer", p["question"], {"question": p["question"], "answer": p["answer"]}, rid)
    return "Svaret er gemt."


# --- forbidden topic ----------------------------------------------------------------------------------------------------

def _v_rule(p: dict) -> dict:
    return {"rule": _text(p.get("rule"), 300, "Reglen")}


def _d_rule(db, ctx, p):
    item, approved, _ = _current(db, ctx.workspace.id, "unknown_answer", p["rule"])
    if item is not None and approved is not None:
        raise Conflict("Den regel findes allerede.", code="assistant_noop")
    return f"Det må den ikke: {p['rule']}", "Ikke på listen", f"Må ikke besvares: {p['rule']}"


def _a_rule(db, ctx, p, rid):
    _publish(db, ctx, "unknown_answer", p["rule"], {"rule": p["rule"]}, rid)
    return "Reglen er tilføjet. Assistenten henviser til et menneske."


# --- booking rules ------------------------------------------------------------------------------------------------------

_BOOK_FIELDS = (("lead_time_hours", 0, 24 * 14, "Tidligste tid"), ("buffer_minutes", 0, 240, "Pausen"), ("horizon_days", 1, 90, "Antal dage frem"))


def _v_booking(p: dict) -> dict:
    out = {k: _int(p[k], lo, hi, name) for k, lo, hi, name in _BOOK_FIELDS if p.get(k) is not None}
    if not out:
        raise _bad("Ingen bookingregel at ændre")
    return out


def _book_text(v: dict) -> str:
    return f"Pause {v['buffer_minutes']} min · tidligst om {v['lead_time_hours']} timer · op til {v['horizon_days']} dage frem"


def _d_booking(db, ctx, p):
    s = bookings.settings(db, ctx.workspace.id)
    cur = {"lead_time_hours": s.lead_time_hours, "buffer_minutes": s.buffer_minutes, "horizon_days": s.horizon_days}
    return "Bookingregler", _book_text(cur), _book_text({**cur, **p})


def _a_booking(db, ctx, p, rid):
    s = bookings.settings(db, ctx.workspace.id, lock=True)
    for k, v in p.items():
        setattr(s, k, v)
    s.version += 1
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="bookings.settings_updated",
                 object_type="booking_settings", object_id=ctx.workspace.id, after=p, request_id=rid)
    return "Bookingreglerne er ændret."


# --- daily report -------------------------------------------------------------------------------------------------------

def _v_report(p: dict) -> dict:
    out: dict = {}
    if p.get("send_hour_local") is not None:
        out["send_hour_local"] = _int(p["send_hour_local"], 0, 23, "Klokkeslættet")
    if isinstance(p.get("email_enabled"), bool):
        out["email_enabled"] = p["email_enabled"]
    if not out:
        raise _bad("Ingen rapportindstilling at ændre")
    return out


def _report_text(v: dict) -> str:
    return f"Dagsrapport kl. {v['send_hour_local']:02d} · {'slået til' if v['email_enabled'] else 'slået fra'}"


def _d_report(db, ctx, p):
    s = reports.settings_for(db, ctx.workspace.id)
    cur = {"email_enabled": s.email_enabled, "send_hour_local": s.send_hour_local}
    return "Dagsrapporten", _report_text(cur), _report_text({**cur, **p})


def _a_report(db, ctx, p, rid):
    s = reports.settings_for(db, ctx.workspace.id)
    before = {"email_enabled": s.email_enabled, "send_hour_local": s.send_hour_local}
    for k, v in p.items():
        setattr(s, k, v)
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="reports.settings_updated",
                 object_type="report_settings", object_id=ctx.workspace.id, before=before,
                 after={"email_enabled": s.email_enabled, "send_hour_local": s.send_hour_local}, request_id=rid)
    return "Dagsrapporten er ændret."


KINDS: dict[str, Kind] = {k.key: k for k in (
    Kind("opening_hours", "Åbningstider", "knowledge.approve",
         'params: {"weekly": [{"days": ["mon","tue",...], "open": "08:00", "close": "16:00"}]} – dage er mon,tue,wed,thu,fri,sat,sun; erstatter ALLE åbningstider.',
         _v_hours, _d_hours, _a_hours, "/app/viden"),
    Kind("service_price", "Pris på en ydelse", "knowledge.approve",
         'params: {"title": "ydelsens navn som i listen", "price_net_minor": hele øre ekskl. moms (145 kr = 14500), "unit": "m2|hour|item|job|null"}.',
         _v_price, _d_price, _a_price, "/app/viden"),
    Kind("known_answer", "Fast svar på et spørgsmål", "knowledge.approve",
         'params: {"question": "...", "answer": "..."} – kun svar kunden selv har givet; opfind aldrig et svar.',
         _v_answer, _d_answer, _a_answer, "/app/viden"),
    Kind("forbidden_topic", "Noget den ikke må svare på", "knowledge.approve",
         'params: {"rule": "kort regel, fx Priser på terrasser uden besigtigelse"}.',
         _v_rule, _d_rule, _a_rule, "/app/viden"),
    Kind("booking_rule", "Bookingregler", "bookings.manage",
         'params: kun de felter der ændres: {"buffer_minutes": 0-240, "lead_time_hours": 0-336, "horizon_days": 1-90}.',
         _v_booking, _d_booking, _a_booking, "/app/aftaler"),
    Kind("report_settings", "Dagsrapport", "reports.manage",
         'params: {"send_hour_local": 0-23, "email_enabled": true|false} – kun de felter der ændres.',
         _v_report, _d_report, _a_report, "/app/ugen"),
)}
