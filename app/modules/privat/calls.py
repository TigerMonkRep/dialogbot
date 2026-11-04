"""«Ring for mig»: calls to businesses on a private user's behalf (add-on "ring-for-mig").

Flow:
1. The chat only PROPOSES a call (task awaiting_user + private_calls row status proposed). Nothing is dialled.
2. approve() locks recipient, number, may_ask/may_agree/may_not, window and share_phone, and requires a verified mobile
   (409 needs_phone) and a weekday 08–18 Copenhagen time (409 outside_hours). Payment: with the trial or a plan and
   quota left, the call is one of the month's plan calls (paid_via 'plan', no credits move); otherwise ≥ 3 credits
   (409 insufficient_credits, extra carries calls_left/needs_plan) are reserved (call:<id>:reserve, paid_via
   'credits'). Then it dials like sales/outbound.dial: the status is committed BEFORE the Vapi request; no answer from
   Vapi = "unknown" (never redialled automatically).
3. The end-of-call report (routed by metadata.private_call_id) captures (call:<id>:capture) when the business
   answered and spoke, or releases (+3, call:<id>:release) on no answer / failure. A plan call moves no credits: a
   lost one simply does not count against the quota. Replays change nothing.
4. A business calling a pool number back is routed by ITS number to the newest open call to it (14 days).
Pool numbers come from PRIVAT_POOL_NUMBERS; Dialogbot never buys numbers here.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, NotImplementedYet, ValidationFailed
from app.models import PhoneNumber, PrivateCall, PrivateProfile, PrivateTask, User, Workspace
from app.modules.privat import addons, ledger, rules, service, sharing, subscriptions

ADDON = "ring-for-mig"
MAX_SECONDS = 180
STALE = timedelta(minutes=30)
FINAL = ("answered", "no_answer", "failed", "declined")
NO_ANSWER_TEXT = "Ingen tog telefonen – dine 3 credits er frigivet"
FAILED_TEXT = "Opkaldet gik ikke igennem – dine 3 credits er frigivet"
PLAN_NO_ANSWER_TEXT = "Ingen tog telefonen – opkaldet tæller ikke"
PLAN_FAILED_TEXT = "Opkaldet gik ikke igennem – opkaldet tæller ikke"
OUTCOME_SYSTEM = """PRIVAT_CALL_OUTCOME
Du får udskriften af et opkald, som en digital assistent har foretaget til en virksomhed på vegne af en privatperson.
Vurder resultatet og svar med ét JSON-objekt og intet andet:
{"outcome": "confirmed" | "callback" | "declined" | "info",
 "confirmed_text": "den aftalte tid kort, fx 'Torsdag kl. 15.30'" eller null,
 "price_text": "en pris virksomheden nævnte, fx '450 kr. for et eftersyn'" eller null,
 "summary": "1-2 sætninger på dansk om hvad virksomheden svarede"}
confirmed = en konkret tid/aftale blev bekræftet; callback = virksomheden ringer tilbage; declined = de kunne ikke/ville ikke;
info = andet svar."""


def _now():
    return rules.now()


# --------------------------------------------------------------------------- pool numbers

def pool() -> list[tuple[str, str | None]]:
    """[(e164, vapi phone-number id or None)] from PRIVAT_POOL_NUMBERS."""
    out = []
    for part in get_settings().privat_pool_numbers.split(","):
        part = part.strip()
        if not part:
            continue
        num, _, pid = part.partition("=")
        out.append((num.strip(), pid.strip() or None))
    return out


def pool_e164s() -> set[str]:
    return {n for n, _ in pool()}


def _pool_for(db: OrmSession, business_e164: str) -> tuple[str, str] | None:
    """The same business always sees the same pool number (so its call-back lands where it expects)."""
    entries = []
    for num, pid in pool():
        if pid is None:
            pid = db.scalar(select(PhoneNumber.provider_number_id).where(PhoneNumber.e164 == num))
        if pid:
            entries.append((num, pid))
    if not entries:
        return None
    i = int(hashlib.sha256(business_e164.encode()).hexdigest(), 16) % len(entries)
    return entries[i]


def problem(db: OrmSession, c: PrivateCall) -> str | None:
    s = get_settings()
    if not s.vapi_api_key or not s.vapi_server_secret:
        return "Opkald er ikke sat op hos Dialogbot endnu."
    if _pool_for(db, c.business_phone_e164) is None:
        return "Dialogbot har ingen numre at ringe fra endnu (PRIVAT_POOL_NUMBERS)."
    return None


# --------------------------------------------------------------------------- proposal

def propose(db: OrmSession, ctx, *, business_name: str, phone: str, address: str, price_text: str | None,
            purpose: str, window: str, may_ask=None, may_agree=None, may_not=None) -> PrivateTask:
    addons.require(db, ctx.ws_id, ADDON)
    purpose = (purpose or "").strip() or "Aftal en tid"
    window = (window or "").strip()
    title = purpose[:1].upper() + purpose[1:]
    if business_name.lower() not in title.lower():
        title = f"{title} hos {business_name}"
    if window and window.lower() not in title.lower():
        title = f"{title} {window}"
    now = _now()
    task = PrivateTask(workspace_id=ctx.ws_id, kind="call", title=title[:300], status="awaiting_user",
                       next_step="Godkend opkaldet", who="Dig", usage_text=pending_usage_text(db, ctx.ws_id),
                       paid_by="call", created_at=now, updated_at=now)
    db.add(task)
    db.flush()
    sharing.add_owner(db, task, ctx.user_id)
    c = PrivateCall(workspace_id=ctx.ws_id, task_id=task.id, business_name=business_name[:200],
                    business_address=address or "", business_phone_e164=phone, business_price_text=price_text,
                    purpose=purpose[:2000], window=window[:200],
                    may_ask=str(may_ask or f"Om de kan {rules.lower_first(purpose)}{' ' + window if window else ''}, "
                                           "og hvad det koster")[:2000],
                    may_agree=str(may_agree or (f"En tid {window}" if window else "Et tidspunkt, der passer"))[:2000],
                    may_not=str(may_not or "Betale, give andre oplysninger end dit navn, eller sige ja til ekstra "
                                           "arbejde eller andre tider")[:2000],
                    status="proposed", created_at=now)
    db.add(c)
    service.event(db, task, "Forslag til opkald oprettet")
    db.flush()
    from app.modules.privat import referrals

    referrals.try_activate(db, ctx.user_id)
    return task


def pending_usage_text(db: OrmSession, ws_id: uuid.UUID) -> str:
    """What approving will cost: the next plan call, or 3 credits."""
    ent = subscriptions.entitlements(db, ws_id)
    if ent["entitled"] and ent["calls_left"] > 0:
        return f"Opkald {ent['calls_used'] + 1} af {ent['calls_quota']} i {subscriptions.plan_label(ent)}, når du godkender"
    return "Højst 3 credits, når du godkender"


def _own_call_task(db: OrmSession, ctx, task_id: uuid.UUID) -> tuple[PrivateTask, PrivateCall]:
    task, m = sharing.access(db, task_id, ctx.user_id, lock=True)
    if task.kind != "call" or m.role != "owner":
        raise NotFound("Opkaldet findes ikke")
    c = db.scalar(select(PrivateCall).where(PrivateCall.task_id == task.id)
                  .order_by(PrivateCall.created_at.desc(), PrivateCall.id).limit(1).with_for_update())
    if c is None:
        raise NotFound("Opkaldet findes ikke")
    return task, c


def approve(db: OrmSession, ctx, task_id: uuid.UUID, *, window: str | None, share_phone: bool) -> PrivateTask:
    addons.require(db, ctx.ws_id, ADDON)
    task, c = _own_call_task(db, ctx, task_id)
    if c.status != "proposed" or task.status != "awaiting_user":
        return task  # already approved (or declined): repeating it changes nothing
    profile = db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == ctx.ws_id).with_for_update())
    if profile.phone_verified_at is None or not profile.phone_e164:
        raise Conflict("Bekræft dit mobilnummer, før assistenten ringer for dig", code="needs_phone")
    ent = subscriptions.entitlements(db, ctx.ws_id)
    use_plan = ent["entitled"] and ent["calls_left"] > 0
    if not use_plan and ledger.balance(db, ctx.ws_id) < rules.CALL_CREDITS:
        raise Conflict("Månedens opkald er brugt – et ekstra opkald reserverer 3 credits" if ent["entitled"]
                       else "Et opkald reserverer 3 credits", code="insufficient_credits",
                       extra={"credits": ledger.balance(db, ctx.ws_id), "needed": rules.CALL_CREDITS,
                              "calls_left": ent["calls_left"], "needs_plan": not ent["entitled"]})
    if not rules.in_call_hours():
        raise Conflict("Assistenten ringer kun til virksomheder på hverdage kl. 8–18", code="outside_hours")
    if c.business_phone_e164 in {f["phone"] for f in _fixtures()} and get_settings().app_env not in ("dev", "test"):
        raise Conflict("Det er et eksempel. Skriv navn og nummer på den rigtige virksomhed.", code="demo_business")
    if (why := problem(db, c)) is not None:
        raise NotImplementedYet(why, code="calls_not_configured")
    if window is not None and window.strip():
        c.window = window.strip()[:200]
    c.share_phone = bool(share_phone)
    now = _now()
    c.status, c.approved_at = "approved", now
    c.approved_snapshot = {"business_name": c.business_name, "business_phone_e164": c.business_phone_e164,
                           "may_ask": c.may_ask, "may_agree": c.may_agree, "may_not": c.may_not, "window": c.window,
                           "share_phone": c.share_phone, "approved_at": now.isoformat()}
    if use_plan:
        c.paid_via = "plan"
        usage = f"Opkald {ent['calls_used'] + 1} af {ent['calls_quota']} i {subscriptions.plan_label(ent)}"
    else:
        c.paid_via = "credits"
        ledger.add(db, ctx.ws_id, kind="reserve", amount=-rules.CALL_CREDITS, source_ref=f"call:{c.id}:reserve",
                   task_id=task.id, text=f"Reserveret til opkald til {c.business_name}")
        usage = "3 credits reserveret"
    task.status, task.next_step, task.who, task.usage_text = "in_progress", "Assistenten ringer op", "Assistenten", usage
    service.event(db, task, f"Du godkendte opkaldet. {usage}.")
    service.touch(task)
    db.commit()
    dial(db, c.id)
    db.refresh(task)
    return task


def decline(db: OrmSession, ctx, task_id: uuid.UUID) -> PrivateTask:
    addons.require(db, ctx.ws_id, ADDON)
    task, c = _own_call_task(db, ctx, task_id)
    if c.status != "proposed":
        if c.status == "declined":
            return task
        raise Conflict("Opkaldet er allerede i gang eller afsluttet", code="call_not_proposed")
    c.status, c.result = "declined", "declined"
    task.status, task.next_step, task.usage_text, task.who = "declined", "Afvist – der er ikke ringet", "Intet forbrug", "Dig"
    service.event(db, task, "Du afviste opkaldet")
    service.touch(task)
    return task


def retry(db: OrmSession, ctx, task_id: uuid.UUID) -> PrivateTask:
    addons.require(db, ctx.ws_id, ADDON)
    task, c = _own_call_task(db, ctx, task_id)
    if c.status == "proposed":
        return task
    if c.status not in ("no_answer", "failed", "declined"):
        raise Conflict("Opkaldet er ikke afsluttet endnu", code="call_running")
    new = PrivateCall(workspace_id=task.workspace_id, task_id=task.id, business_name=c.business_name,
                      business_address=c.business_address, business_phone_e164=c.business_phone_e164,
                      business_price_text=c.business_price_text, purpose=c.purpose, may_ask=c.may_ask,
                      may_agree=c.may_agree, may_not=c.may_not, window=c.window, share_phone=c.share_phone,
                      status="proposed", created_at=max(_now(), c.created_at + timedelta(microseconds=1)))
    db.add(new)
    task.status, task.next_step, task.who, task.usage_text = "awaiting_user", "Godkend opkaldet", "Dig", \
        pending_usage_text(db, ctx.ws_id)
    service.event(db, task, "Nyt forslag til opkald")
    service.touch(task)
    db.flush()
    service.add_message(db, ctx.ws_id, kind="call_proposal", text=f"Skal jeg prøve {c.business_name} igen?",
                        task_id=task.id)
    return task


def _fixtures() -> tuple:
    from app.modules.privat.chat import FIXTURES

    return FIXTURES


# --------------------------------------------------------------------------- dialling

def script(c: PrivateCall, user: User) -> tuple[str, str]:
    """(first message, system prompt) for the outbound call."""
    name = user.display_name
    first = (f"Hej, jeg ringer fra Dialogbot på vegne af {name}. Jeg er en digital assistent. "
             f"Det drejer sig om: {rules.lower_first(c.purpose)}{' ' + c.window if c.window else ''}. Har du et øjeblik?")
    system = f"""Du er Dialogbot, en dansk digital assistent, der ringer til virksomheden {c.business_name} på vegne af
privatpersonen {name}. Du har allerede sagt, at du er en digital assistent. Lyv aldrig om at være et menneske.

Formål: {c.purpose}{' ' + c.window if c.window else ''}
Du må spørge om: {c.may_ask}
Du må sige ja til: {c.may_agree}
Du må IKKE: {c.may_not}

Regler:
- Opkaldet er kort (højst {MAX_SECONDS // 60} minutter). Ét spørgsmål ad gangen, naturligt dansk talesprog.
- Sig kun {name}s navn. Giv aldrig telefonnummer, adresse, e-mail eller andre oplysninger
  {"(du må give mobilnummeret, hvis virksomheden beder om det)" if c.share_phone else ""}.
- Siger virksomheden en tid inden for det, du må sige ja til, så bekræft den ved at gentage dag og klokkeslæt.
- Kan de ikke svare nu, så sig at de kan ringe tilbage til dette nummer, og at {name} får besked.
- Hvis de ikke vil tale med en assistent, så undskyld og afslut straks.
- Afslut kort og venligt med "Tak for hjælpen, hav en god dag"."""
    return first, system


def assistant_for(db: OrmSession, c: PrivateCall, user: User) -> dict:
    from app.modules.telephony import vapi

    s = get_settings()
    first, system = script(c, user)
    assistant: dict = {
        "firstMessage": first,
        "model": {"provider": s.vapi_model_provider, "model": vapi.phone_model(s),
                  "messages": [{"role": "system", "content": system}], "tools": [vapi.END_CALL_TOOL]},
        "transcriber": vapi.transcriber_for(db, None, extra=[c.business_name, *user.display_name.split()]),
        "maxDurationSeconds": MAX_SECONDS,
        "voicemailDetection": {"provider": "vapi"},
        "endCallPhrases": ["Tak for hjælpen, hav en god dag", *vapi.END_CALL_PHRASES],
        "analysisPlan": {"summaryPlan": {"messages": [
            {"role": "system", "content": "Du er referent. Opsummér på dansk i 1-2 sætninger, hvad virksomheden svarede "
                                          "på privatpersonens vegne, inkl. en aftalt tid eller pris. Returnér kun resuméet."},
            {"role": "user", "content": "Udskrift:\n\n{{transcript}}\n\nÅrsag til afslutning: {{endedReason}}"}]}},
        "stopSpeakingPlan": vapi.STOP_SPEAKING_PLAN, "startSpeakingPlan": vapi.START_SPEAKING_PLAN,
        "metadata": {"private_call_id": str(c.id), "private_task_id": str(c.task_id)},
    }
    if (voice := vapi._json_setting(s.vapi_voice_json)) is not None:
        assistant["voice"] = voice
    if (server := vapi.server_block()) is not None:
        assistant["server"] = server
    return vapi.apply_pacing(assistant)


def dial(db: OrmSession, call_id: uuid.UUID) -> None:
    """Status committed BEFORE the provider is called; the answer is stored afterwards."""
    from app.modules.campaigns import service as campaigns

    c = db.scalar(select(PrivateCall).where(PrivateCall.id == call_id).with_for_update())
    if c is None or c.status != "approved":
        return
    user = db.get(User, db.scalar(select(PrivateProfile.user_id).where(PrivateProfile.workspace_id == c.workspace_id)))
    pool_num, pool_id = _pool_for(db, c.business_phone_e164)
    now = _now()
    c.status, c.pool_number, c.dialled_at, c.expires_at = "dialling", pool_num, now, now + timedelta(days=rules.CALLBACK_DAYS)
    assistant = assistant_for(db, c, user)
    db.commit()
    payload = {"phoneNumberId": pool_id, "customer": {"number": c.business_phone_e164, "name": c.business_name[:40]},
               "assistant": assistant, "metadata": {"private_call_id": str(c.id), "private_task_id": str(c.task_id)}}
    try:
        out = campaigns.create_call(payload)
    except ApiError as e:
        c = db.scalar(select(PrivateCall).where(PrivateCall.id == call_id).with_for_update())
        task = db.get(PrivateTask, c.task_id)
        if (e.extra or {}).get("no_response"):
            # the call may exist at Vapi: wait for a report (or the stale sweep), never redial by ourselves
            c.status = "unknown"
            service.event(db, task, "Telefontjenesten svarede ikke – vi venter på besked om opkaldet")
        else:
            _release(db, c, task, result="failed", reason=e.message[:100])
        db.commit()
        return
    c = db.scalar(select(PrivateCall).where(PrivateCall.id == call_id).with_for_update())
    c.vapi_call_id = str(out.get("id") or "")[:100] or None
    c.status = "in_progress"
    db.commit()


# --------------------------------------------------------------------------- results

def _release(db: OrmSession, c: PrivateCall, task: PrivateTask, *, result: str, reason: str | None) -> None:
    c.status, c.result, c.ended_reason, c.ended_at = result, result, (reason or "")[:100] or None, _now()
    if c.paid_via == "plan":
        # nothing was reserved: a lost plan call is simply left out of the month's count (subscriptions.calls_used)
        text = PLAN_NO_ANSWER_TEXT if result == "no_answer" else PLAN_FAILED_TEXT
    else:
        ledger.add(db, c.workspace_id, kind="release", amount=rules.CALL_CREDITS, source_ref=f"call:{c.id}:release",
                   task_id=task.id, text="Ingen svar – reservation frigivet" if result == "no_answer"
                   else "Opkaldet gik ikke igennem – reservation frigivet")
        text = NO_ANSWER_TEXT if result == "no_answer" else FAILED_TEXT
    task.status, task.next_step, task.who, task.usage_text = "awaiting_user", "Prøv igen eller annullér", "Dig", \
        "Intet forbrug – ingen svarede" if result == "no_answer" else "Intet forbrug"
    service.event(db, task, text)
    service.touch(task)
    service.add_message(db, c.workspace_id, kind="text", text=f"{text}.", task_id=task.id)
    service.notify_owner(db, task, subject=f"Opkald til {c.business_name}", text=f"{text}.", dedupe=f"call:{c.id}:release")


def classify(db: OrmSession, ws: Workspace, transcript: str, summary: str) -> dict:
    from app.modules.ai.provider import get_provider
    from app.modules.ai.service import log_call

    data: dict = {}
    try:
        comp, _row = log_call(db, ws, get_provider(), user_id=None, purpose="privat_call_outcome", system=OUTCOME_SYSTEM,
                              messages=[{"role": "user", "content": (transcript or summary)[:12000]}],
                              prompt_version="privat-outcome-v1", revision=0, max_tokens=400)
        t = comp.text
        data = json.loads(t[t.find("{"):t.rfind("}") + 1]) if "{" in t else {}
    except (ApiError, ValueError):
        data = {}
    if data.get("outcome") not in ("confirmed", "callback", "declined", "info"):
        data["outcome"] = "info"
    return data


def _meta(message: dict) -> dict:
    from app.modules.telephony.vapi import _dig

    for path in (("call", "metadata"), ("call", "assistant", "metadata"), ("assistant", "metadata"), ("metadata",)):
        v = _dig(message, *path)
        if isinstance(v, dict) and (v.get("private_call_id") or v.get("private_callback")):
            return v
    return {}


def _lines(message: dict) -> tuple[int, str]:
    from app.modules.telephony import vapi

    n, lines = 0, []
    for m in vapi.transcript_messages(message):
        role = vapi.ROLE.get(str(m.get("role", "")).lower())
        text = str(m.get("message") or m.get("content") or "").strip()
        if not role or not text:
            continue
        n += role == "visitor"
        lines.append(("Virksomhed" if role == "visitor" else "Assistent") + ": " + text)
    return n, "\n".join(lines)


def on_report(db: OrmSession, message: dict) -> str | None:
    """End-of-call report for a private call (outbound or a call-back). None = not ours."""
    from app.modules.campaigns.service import NO_ANSWER_REASONS
    from app.modules.telephony.vapi import _dig

    meta = _meta(message)
    call_id = str(_dig(message, "call", "id") or "")
    if meta.get("private_callback"):
        return on_callback_report(db, message, meta)
    c = None
    if meta.get("private_call_id"):
        try:
            c = db.scalar(select(PrivateCall).where(PrivateCall.id == uuid.UUID(str(meta["private_call_id"])))
                          .with_for_update())
        except ValueError:
            c = None
    if c is None and call_id:
        c = db.scalar(select(PrivateCall).where(PrivateCall.vapi_call_id == call_id).with_for_update())
    if c is None:
        return None
    if c.status in FINAL:
        return "duplicate"
    task = db.get(PrivateTask, c.task_id)
    if call_id and not c.vapi_call_id:
        c.vapi_call_id = call_id[:100]
    reason = str(message.get("endedReason") or "")
    visitor_lines, transcript = _lines(message)
    duration = message.get("durationSeconds")
    summary = str(_dig(message, "analysis", "summary") or message.get("summary") or "")[:4000]
    answered = visitor_lines > 0 and not any(reason.startswith(r) for r in NO_ANSWER_REASONS)
    if not answered:
        no_answer = any(reason.startswith(r) for r in NO_ANSWER_REASONS) or visitor_lines == 0
        _release(db, c, task, result="no_answer" if no_answer else "failed", reason=reason)
        return "applied"
    c.status, c.result, c.ended_reason, c.ended_at = "answered", "answered", reason[:100] or None, _now()
    c.duration_seconds = int(duration) if isinstance(duration, int | float) else None
    if c.paid_via == "plan":
        ent = subscriptions.entitlements(db, c.workspace_id)
        quota = ent["calls_quota"] or subscriptions.PLANS[subscriptions.TRIAL_PLAN]["calls"]
        charged = f"Opkald {subscriptions.plan_call_index(db, c)} af {quota} i {subscriptions.plan_label(ent)}"
        task.usage_text = f"{charged} · besvaret{_dur(c.duration_seconds)}"
    else:
        ledger.add(db, c.workspace_id, kind="capture", amount=0, source_ref=f"call:{c.id}:capture", task_id=task.id,
                   text=f"Opkald til {c.business_name} · besvaret{_dur(c.duration_seconds)}")
        charged = "3 credits trukket"
        task.usage_text = f"3 credits · besvaret opkald{_dur(c.duration_seconds)}"
    data = classify(db, db.get(Workspace, c.workspace_id), transcript, summary)
    c.business_reply = str(data.get("summary") or summary or "")[:4000] or None
    if data.get("price_text"):
        c.business_price_text = str(data["price_text"])[:300]
    if data["outcome"] == "confirmed" and data.get("confirmed_text"):
        c.confirmed_text = str(data["confirmed_text"])[:300]
        task.status, task.next_step, task.who = "done", c.confirmed_text, f"{c.business_name} har bekræftet"
        text = f"Opkaldet er slut. {c.business_name} har bekræftet {rules.lower_first(c.confirmed_text)}."
    elif data["outcome"] == "callback":
        task.status, task.next_step, task.who = "awaiting_business", f"{c.business_name} ringer tilbage", c.business_name
        text = f"Opkaldet er slut. {c.business_name} ringer tilbage – du får besked."
    else:
        task.status, task.next_step, task.who = "done", "Se svaret fra virksomheden", "Dig"
        text = f"Opkaldet er slut. {c.business_name} svarede: {c.business_reply or 'se opgaven'}"
    service.event(db, task, f"Opkaldet blev besvaret. {c.business_reply or ''}".strip())
    service.event(db, task, charged)
    service.touch(task)
    service.add_message(db, c.workspace_id, kind="text", text=text, task_id=task.id)
    service.notify_owner(db, task, subject=f"Opkald til {c.business_name}", text=text, dedupe=f"call:{c.id}:answered")
    return "applied"


def _dur(seconds: int | None) -> str:
    if not seconds:
        return ""
    m, s = divmod(int(seconds), 60)
    return f", {m} min. {s} sek." if m else f", {s} sek."


def sweep_stale(db: OrmSession) -> int:
    """Calls that never got a report: release the reservation after 30 minutes (worker schedule)."""
    cutoff = _now() - STALE
    rows = list(db.scalars(select(PrivateCall).where(PrivateCall.status.in_(("dialling", "unknown", "in_progress")),
                                                     PrivateCall.dialled_at < cutoff).with_for_update(skip_locked=True)))
    for c in rows:
        _release(db, c, db.get(PrivateTask, c.task_id), result="failed", reason="no-report")
    db.commit()
    return len(rows)


# --------------------------------------------------------------------------- call-backs to pool numbers

def is_pool_call(message: dict) -> bool:
    from app.modules.telephony.vapi import _dig, normalize_e164

    entries = pool()
    if not entries:
        return False
    org = get_settings().vapi_org_id
    msg_org = _dig(message, "call", "orgId") or _dig(message, "phoneNumber", "orgId")
    if org and msg_org and str(msg_org) != org:
        return False
    pid = _dig(message, "call", "phoneNumberId") or _dig(message, "phoneNumber", "id")
    num = _dig(message, "phoneNumber", "number") or _dig(message, "call", "phoneNumber", "number")
    num = normalize_e164(str(num)) if num else None
    return any((num and num == n) or (pid and p and str(pid) == p) for n, p in entries)


def open_calls_from(db: OrmSession, business_e164: str) -> list[PrivateCall]:
    """Newest open call per user to this business within 14 days."""
    now = _now()
    rows = db.scalars(select(PrivateCall).where(
        PrivateCall.business_phone_e164 == business_e164, PrivateCall.expires_at > now,
        PrivateCall.status.not_in(("proposed", "declined"))).order_by(PrivateCall.dialled_at.desc()))
    seen, out = set(), []
    for c in rows:
        if c.workspace_id not in seen:
            seen.add(c.workspace_id)
            out.append(c)
    return out


def _user_of(db: OrmSession, ws_id: uuid.UUID) -> tuple[User, PrivateProfile]:
    p = db.scalar(select(PrivateProfile).where(PrivateProfile.workspace_id == ws_id))
    return db.get(User, p.user_id), p


def callback_assistant(db: OrmSession, message: dict) -> dict:
    """assistant-request on a pool number: routed by the CALLER's number. One user → on their behalf; several →
    asks which person; unknown caller → a polite generic message without any personal data."""
    from app.modules.campaigns.service import normalize_phone
    from app.modules.telephony import vapi

    s = get_settings()
    raw = vapi._dig(message, "call", "customer", "number") or vapi._dig(message, "customer", "number")
    caller = normalize_phone(str(raw)) if raw else None
    calls = open_calls_from(db, caller) if caller else []
    base = {"model": {"provider": s.vapi_model_provider, "model": vapi.phone_model(s), "tools": [vapi.END_CALL_TOOL]},
            "transcriber": vapi.transcriber_for(db, None), "stopSpeakingPlan": vapi.STOP_SPEAKING_PLAN,
            "startSpeakingPlan": vapi.START_SPEAKING_PLAN, "endCallPhrases": vapi.END_CALL_PHRASES}
    if (voice := vapi._json_setting(s.vapi_voice_json)) is not None:
        base["voice"] = voice
    if (server := vapi.server_block()) is not None:
        base["server"] = server
    if not calls:
        return {"assistant": base | {
            "firstMessage": "Hej, du har ringet til Dialogbot, en digital assistent. Jeg kan desværre ikke se en "
                            "henvendelse fra dette nummer, så jeg kan ikke hjælpe dig her. Tak for opkaldet, hav en god dag.",
            "maxDurationSeconds": 30,
            "model": base["model"] | {"messages": [{"role": "system", "content":
                                                    "Sig kun farvel. Giv ingen oplysninger om nogen person."}]},
            "metadata": {"private_callback": True, "private_call_ids": []}}}
    names = []
    for c in calls:
        u, _p = _user_of(db, c.workspace_id)
        names.append((c, u))
    if len(names) == 1:
        c, u = names[0]
        _u, p = _user_of(db, c.workspace_id)
        first = (f"Hej, du har ringet til Dialogbot. Jeg er en digital assistent og ringede til jer på vegne af "
                 f"{u.display_name} om: {rules.lower_first(c.purpose)}. Hvad kan jeg give videre?")
        system = (f"Du er Dialogbot, en dansk digital assistent. {c.business_name} ringer tilbage om {u.display_name}s "
                  f"henvendelse: {c.purpose} {c.window}. Du må sige ja til: {c.may_agree}. Du må IKKE: {c.may_not}. "
                  f"Tag imod beskeden eller bekræftelsen, gentag en aftalt tid, og sig at {u.display_name} får besked. "
                  "Giv aldrig telefonnummer, adresse eller andre oplysninger om personen. Afslut med 'hav en god dag'.")
        a = base | {"firstMessage": first, "maxDurationSeconds": MAX_SECONDS,
                    "model": base["model"] | {"messages": [{"role": "system", "content": system}]},
                    "metadata": {"private_callback": True, "private_call_ids": [str(c.id)]}}
        if c.share_phone and p.phone_verified_at and p.phone_e164:
            a["model"]["tools"] = [*a["model"]["tools"], {
                "type": "transferCall", "destinations": [{"type": "number", "number": p.phone_e164,
                                                          "message": f"Et øjeblik, jeg stiller dig om til {u.display_name}."}]}]
            a["model"]["messages"][0]["content"] += (f" Vil virksomheden tale med {u.display_name} selv, må du stille "
                                                     "om med værktøjet transferCall.")
        return {"assistant": a}
    firsts = [rules.first_name(u.display_name) for _c, u in names]
    listed = ", ".join(firsts[:-1]) + " eller " + firsts[-1]
    system = ("Du er Dialogbot, en dansk digital assistent. Virksomheden ringer tilbage, og vi har ringet til den for "
              f"flere personer: {listed}. Spørg hvem det drejer sig om, før du tager imod beskeden. Sig personens navn "
              "tilbage, når du har fået det. Giv aldrig oplysninger om nogen af personerne. Afslut med 'hav en god dag'.")
    return {"assistant": base | {
        "firstMessage": "Hej, du har ringet til Dialogbot, en digital assistent. Vi har ringet til jer for flere "
                        "personer – hvem drejer det sig om?",
        "maxDurationSeconds": MAX_SECONDS,
        "model": base["model"] | {"messages": [{"role": "system", "content": system}]},
        "metadata": {"private_callback": True, "private_call_ids": [str(c.id) for c, _u in names]}}}


def on_callback_report(db: OrmSession, message: dict, meta: dict) -> str:
    ids = [uuid.UUID(x) for x in meta.get("private_call_ids") or [] if re.fullmatch(r"[0-9a-f-]{36}", str(x))]
    visitor_lines, transcript = _lines(message)
    if not ids or not visitor_lines:
        return "ignored"
    from app.modules.telephony.vapi import _dig

    calls = [db.get(PrivateCall, i) for i in ids]
    calls = [c for c in calls if c is not None]
    if len(calls) > 1:  # several people: only the one the business named
        low = transcript.lower()
        hits = [c for c in calls if rules.first_name(_user_of(db, c.workspace_id)[0].display_name).lower() in low]
        calls = hits if len(hits) == 1 else []
    if not calls:
        return "unmatched"
    c = calls[0]
    task = db.get(PrivateTask, c.task_id)
    summary = str(_dig(message, "analysis", "summary") or "")[:4000]
    data = classify(db, db.get(Workspace, c.workspace_id), transcript, summary)
    reply = str(data.get("summary") or summary or "")[:4000]
    c.business_reply = reply or c.business_reply
    if data["outcome"] == "confirmed" and data.get("confirmed_text"):
        c.confirmed_text = str(data["confirmed_text"])[:300]
        task.status, task.next_step, task.who = "done", c.confirmed_text, f"{c.business_name} har bekræftet"
    elif task.status == "awaiting_business":
        task.status, task.next_step = "done", "Se svaret fra virksomheden"
    text = f"{c.business_name} ringede tilbage: {reply or 'se opgaven'}"
    service.event(db, task, text)
    service.touch(task)
    service.add_message(db, c.workspace_id, kind="text", text=text, task_id=task.id)
    service.notify_owner(db, task, subject=f"{c.business_name} ringede tilbage", text=text,
                         dedupe=f"callback:{_dig(message, 'call', 'id') or uuid.uuid4()}")
    return "applied"


def validate_window(window: str | None) -> str | None:
    if window is not None and len(window) > 200:
        raise ValidationFailed("Tidsrummet er for langt", field_errors=[{"field": "window"}])
    return window
