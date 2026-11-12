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
from app.core.languages import LANGUAGES, NAME_DA
from app.models import (
    BusinessProfile,
    KnowledgeItem,
    KnowledgeVersion,
    LanguageSettings,
    PhoneNumber,
    ReceptionScript,
    WebchatSettings,
)
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


# --- reception manuscript: greeting, name and form of address, hand-over -------------------------------------------------

def _script(db: OrmSession, ctx: WorkspaceContext, lock: bool = False) -> ReceptionScript | None:
    q = select(ReceptionScript).where(ReceptionScript.workspace_id == ctx.workspace.id)
    return db.scalar(q.with_for_update() if lock else q)


def _save_script(db: OrmSession, ctx: WorkspaceContext, changes: dict, rid: str | None) -> None:
    """The same write as PUT /reception/script: one new version, audited."""
    from app.modules.reception import service as reception

    s = _script(db, ctx, lock=True)
    before = {k: getattr(s, k) for k in reception.FIELDS} if s else None
    if s is None:
        s = ReceptionScript(workspace_id=ctx.workspace.id, version=0, address_form="du", collect=[])
        db.add(s)
    for k, v in changes.items():
        setattr(s, k, v)
    s.version = (s.version or 0) + 1
    s.updated_by = ctx.user_id
    db.flush()
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="reception.script_updated",
                 object_type="reception_script", object_id=ctx.workspace.id, before=before,
                 after={k: getattr(s, k) for k in reception.FIELDS}, request_id=rid)


def _own_number_greeting(db: OrmSession, ws_id: uuid.UUID) -> bool:
    return any(n.greeting.strip() for n in db.scalars(select(PhoneNumber).where(
        PhoneNumber.workspace_id == ws_id, PhoneNumber.status != "released")))


def _v_greeting(p: dict) -> dict:
    return {"greeting": _text(p.get("greeting"), 400, "Hilsenen")}


def _d_greeting(db, ctx, p):
    if _own_number_greeting(db, ctx.workspace.id):
        raise Conflict("Jeres telefonnummer har sin egen hilsen, som går forud. Ret den under Alle indstillinger → Telefon.",
                       code="assistant_noop")
    s = _script(db, ctx)
    return "Hilsen i telefonen og chatten", (s.greeting if s and s.greeting else "Standardhilsen"), p["greeting"]


def _a_greeting(db, ctx, p, rid):
    _save_script(db, ctx, {"greeting": p["greeting"]}, rid)
    return "Hilsenen er ændret."


def _v_persona(p: dict) -> dict:
    out: dict = {}
    if p.get("persona_name") is not None:
        out["persona_name"] = re.sub(r"\s+", " ", str(p["persona_name"])).strip()[:60]
    if p.get("address_form") is not None:
        if p["address_form"] not in ("du", "De"):
            raise _bad("Tiltaleformen skal være du eller De")
        out["address_form"] = p["address_form"]
    if not out:
        raise _bad("Intet at ændre ved navn eller tiltale")
    return out


def _persona_text(name: str, form: str) -> str:
    return f"{'Navn: ' + name if name else 'Intet navn'} · siger {form}"


def _d_persona(db, ctx, p):
    s = _script(db, ctx)
    cur = {"persona_name": s.persona_name if s else "", "address_form": s.address_form if s else "du"}
    new = {**cur, **p}
    return "Navn og tiltale", _persona_text(cur["persona_name"], cur["address_form"]), _persona_text(new["persona_name"], new["address_form"])


def _a_persona(db, ctx, p, rid):
    _save_script(db, ctx, p, rid)
    return "Navn og tiltale er ændret."


def _v_escalation(p: dict) -> dict:
    return {"escalation": _text(p.get("escalation"), 800, "Hvornår en medarbejder skal overtage")}


def _d_escalation(db, ctx, p):
    s = _script(db, ctx)
    return "Hvornår en medarbejder overtager", (s.escalation if s and s.escalation else "Ikke angivet"), p["escalation"]


def _a_escalation(db, ctx, p, rid):
    _save_script(db, ctx, {"escalation": p["escalation"]}, rid)
    return "Det er gemt. Assistenten giver videre til en medarbejder i de situationer."


# --- conversation languages -----------------------------------------------------------------------------------------------

def _lang(v: Any) -> str:
    c = str(v or "").strip().lower()
    c = "no" if c in ("nb", "nn") else c
    if c not in LANGUAGES:
        raise _bad("Det sprog findes ikke i Dialogbot")
    return c


def _v_languages(p: dict) -> dict:
    out: dict = {}
    if p.get("default") is not None:
        out["default"] = _lang(p["default"])
    if isinstance(p.get("enabled"), list) and p["enabled"]:
        out["enabled"] = list(dict.fromkeys(_lang(x) for x in p["enabled"][:len(LANGUAGES)]))
    if not out:
        raise _bad("Intet sprog at ændre")
    return out


def _lang_text(default: str, enabled: list[str]) -> str:
    others = [NAME_DA[c] for c in enabled if c != default and c in NAME_DA]
    return f"Standard {NAME_DA.get(default, default)}" + (f" · også {', '.join(others)}" if others else "")


def _lang_new(cur: LanguageSettings, p: dict) -> tuple[str, list[str]]:
    from app.core.languages import normalize

    default = p.get("default") or normalize(cur.default_conversation_language)
    enabled = p.get("enabled") or [normalize(x) for x in cur.enabled_conversation_languages or []]
    if default not in enabled:
        enabled = [default, *enabled]
    return default, list(dict.fromkeys(enabled))


def _d_languages(db, ctx, p):
    from app.core.languages import normalize

    cur = db.get(LanguageSettings, ctx.workspace.id)
    if cur is None:
        raise Conflict("Sprogindstillingerne findes ikke endnu. Udfyld trin 1 først.", code="assistant_noop")
    before = _lang_text(normalize(cur.default_conversation_language), [normalize(x) for x in cur.enabled_conversation_languages or []])
    return "Samtalesprog", before, _lang_text(*_lang_new(cur, p))


def _a_languages(db, ctx, p, rid):
    from app.modules.setup.checks import invalidate_checks

    ls = db.scalar(select(LanguageSettings).where(LanguageSettings.workspace_id == ctx.workspace.id).with_for_update())
    before = {"default_conversation_language": ls.default_conversation_language, "enabled_conversation_languages": list(ls.enabled_conversation_languages)}
    ls.default_conversation_language, ls.enabled_conversation_languages = _lang_new(ls, p)
    ls.version += 1
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="languages.updated",
                 object_type="language_settings", object_id=ctx.workspace.id, before=before,
                 after={"default_conversation_language": ls.default_conversation_language,
                        "enabled_conversation_languages": ls.enabled_conversation_languages}, request_id=rid)
    invalidate_checks(db, ctx.workspace.id, changed_area="languages", reason="Sprogindstillinger blev ændret")
    return "Samtalesprogene er ændret."


# --- standard voice -------------------------------------------------------------------------------------------------------

def _v_voice(p: dict) -> dict:
    from app.modules.voices import standard

    key = str(p.get("voice") or "").strip().lower()
    if key not in standard.STANDARD_VOICES:
        raise _bad("Vælg en af standardstemmerne: " + ", ".join(v["name"] for v in standard.STANDARD_VOICES.values()))
    return {"voice": key}


def _voice_text(db, ws_id) -> str:
    from app.modules.voices import service as voices
    from app.modules.voices import standard

    s = voices.settings(db, ws_id)
    if s.default_profile_id:
        return "Egen stemme"
    return standard.STANDARD_VOICES[standard.chosen(db, ws_id) or standard.DEFAULT]["name"]


def _d_voice(db, ctx, p):
    from app.modules.voices import standard

    if any(n.voice_id.strip() for n in db.scalars(select(PhoneNumber).where(PhoneNumber.workspace_id == ctx.workspace.id,
                                                                            PhoneNumber.status != "released"))):
        raise Conflict("Jeres telefonnummer har sin egen stemme valgt, som går forud. Skift den under Alle indstillinger → Telefon.",
                       code="assistant_noop")
    return "Stemme i telefonen", _voice_text(db, ctx.workspace.id), standard.STANDARD_VOICES[p["voice"]]["name"]


def _a_voice(db, ctx, p, rid):
    from datetime import UTC, datetime

    from app.modules.setup.checks import invalidate_checks
    from app.modules.voices import service as voices

    s = voices.settings(db, ctx.workspace.id, lock=True)
    s.standard_voice, s.default_profile_id, s.last_preview = p["voice"], None, None
    s.version += 1
    s.updated_at = datetime.now(UTC)
    invalidate_checks(db, ctx.workspace.id, changed_area="voice", reason="voices.settings_updated")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="voices.settings_updated",
                 object_type="workspace_voice_settings", object_id=ctx.workspace.id,
                 after={"default_profile_id": None, "standard_voice": p["voice"], "fallback": s.fallback}, request_id=rid)
    return "Stemmen er skiftet. Hør den under Stemme."


# --- webchat greeting -----------------------------------------------------------------------------------------------------

def _v_webchat(p: dict) -> dict:
    return {"greeting": _text(p.get("greeting"), 300, "Velkomsten")}


def _d_webchat(db, ctx, p):
    s = db.get(WebchatSettings, ctx.workspace.id)
    return "Velkomst i webchatten", (s.greeting if s and s.greeting else "Standardvelkomst"), p["greeting"]


def _a_webchat(db, ctx, p, rid):
    from app.modules.setup.checks import invalidate_checks
    from app.modules.webchat import service as webchat

    webchat.get_or_create(db, ctx.workspace.id)
    s = db.scalar(select(WebchatSettings).where(WebchatSettings.workspace_id == ctx.workspace.id).with_for_update())
    before = {"enabled": s.enabled, "allowed_origins": list(s.allowed_origins), "greeting": s.greeting}
    s.greeting = p["greeting"]
    s.version += 1
    invalidate_checks(db, ctx.workspace.id, changed_area="integrations", reason="webchat.updated")
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="webchat.updated",
                 object_type="webchat_settings", object_id=ctx.workspace.id, before=before,
                 after={**before, "greeting": s.greeting}, request_id=rid)
    return "Velkomsten i webchatten er ændret."


# --- business profile -----------------------------------------------------------------------------------------------------

PROFILE_FIELDS = {"phone": ("Telefon", 40), "website_url": ("Hjemmeside", 500), "address_line": ("Adresse", 300),
                  "postal_code": ("Postnummer", 16), "city": ("By", 120), "description": ("Hvad I laver", 4000)}


def _v_profile(p: dict) -> dict:
    out: dict = {}
    for k, (name, n) in PROFILE_FIELDS.items():
        if p.get(k) is None:
            continue
        v = _text(p[k], n, name) if k == "description" else re.sub(r"\s+", " ", str(p[k])).strip()[:n]
        if k == "website_url" and v:
            if not re.match(r"^https?://", v):
                v = "https://" + v
            if not re.fullmatch(r"https?://[\w.-]+\.[a-z]{2,}(/\S*)?", v, re.I):
                raise _bad("Hjemmesidens adresse kunne ikke læses")
        if k == "phone" and v and not re.fullmatch(r"\+?[\d ]{8,20}", v):
            raise _bad("Telefonnummeret kunne ikke læses")
        if k == "postal_code" and v and not re.fullmatch(r"\d{3,5}", v):
            raise _bad("Postnummeret kunne ikke læses")
        out[k] = v or None if k != "description" else v
    if not out:
        raise _bad("Intet at ændre i virksomhedsoplysningerne")
    return out


def _profile_text(vals: dict, keys) -> str:
    return " · ".join(f"{PROFILE_FIELDS[k][0]}: {(vals.get(k) or '–')[:120]}" for k in keys)


def _d_profile(db, ctx, p):
    prof = db.get(BusinessProfile, ctx.workspace.id)
    if prof is None:
        raise Conflict("Virksomhedsprofilen findes ikke endnu. Udfyld trin 1 først.", code="assistant_noop")
    cur = {k: getattr(prof, k) for k in p}
    return "Virksomhedsoplysninger", _profile_text(cur, p), _profile_text(p, p)


def _a_profile(db, ctx, p, rid):
    from app.modules.setup.checks import invalidate_checks

    prof = db.scalar(select(BusinessProfile).where(BusinessProfile.workspace_id == ctx.workspace.id).with_for_update())
    before = {k: getattr(prof, k) for k in PROFILE_FIELDS}
    for k, v in p.items():
        setattr(prof, k, v)
    prof.version += 1
    record_audit(db, workspace_id=ctx.workspace.id, actor_user_id=ctx.user_id, action="profile.updated",
                 object_type="business_profile", object_id=ctx.workspace.id, before=before,
                 after={k: getattr(prof, k) for k in PROFILE_FIELDS}, request_id=rid)
    invalidate_checks(db, ctx.workspace.id, changed_area="profile", reason="Virksomhedsprofilen blev ændret")
    return "Virksomhedsoplysningerne er ændret."


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
    Kind("greeting", "Hilsen", "reception.manage",
         'params: {"greeting": "det assistenten siger først i telefonen og chatten, højst 400 tegn; {virksomhed} = firmanavnet"} – kun en hilsen personen selv har formuleret eller bedt om.',
         _v_greeting, _d_greeting, _a_greeting, "/app/indstillinger?ark=hilsen"),
    Kind("persona", "Navn og tiltale", "reception.manage",
         'params: {"persona_name": "navnet assistenten præsenterer sig med", "address_form": "du|De"} – kun de felter der ændres.',
         _v_persona, _d_persona, _a_persona, "/app/indstillinger?ark=hilsen"),
    Kind("escalation", "Hvornår en medarbejder overtager", "reception.manage",
         'params: {"escalation": "de situationer hvor den straks skal give videre til en medarbejder"} – erstatter hele teksten; tag det eksisterende med, hvis personen tilføjer noget.',
         _v_escalation, _d_escalation, _a_escalation, "/app/indstillinger?ark=hilsen"),
    Kind("conversation_languages", "Samtalesprog", "languages.edit",
         'params: {"default": "da|en|de|es|fr|it|no|sv", "enabled": ["da","en",...]} – default er det sprog den starter på; enabled er alle sprog den må tale. Kun de felter der ændres.',
         _v_languages, _d_languages, _a_languages, "/app/indstillinger?ark=telefoni"),
    Kind("standard_voice", "Stemme", "voices.manage",
         'params: {"voice": "camilla|peter"} – Camilla (kvinde, rigsdansk) eller Peter (mand, let jysk). Skifter fra egen stemme til standardstemmen.',
         _v_voice, _d_voice, _a_voice, "/app/indstillinger?ark=stemmer"),
    Kind("webchat_greeting", "Velkomst i webchatten", "webchat.manage",
         'params: {"greeting": "det webchatten skriver først, højst 300 tegn"}.',
         _v_webchat, _d_webchat, _a_webchat, "/app/indstillinger?ark=webchat"),
    Kind("business_profile", "Virksomhedsoplysninger", "profile.edit",
         'params: kun de felter der ændres: {"phone": "+45 …", "website_url": "https://…", "address_line": "…", "postal_code": "8000", "city": "…", "description": "hvad virksomheden laver"}.',
         _v_profile, _d_profile, _a_profile, "/opsaetning/virksomhed"),
)}
