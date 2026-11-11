"""QA harness for e2e-privat (X07/X09/X11): the REAL FastAPI app + worker with Dialogbot Privat switched on, on its own
port and its own database, with Stripe and Vapi replaced in-process – the same seams the pytest suite uses
(`app.modules.billing.stripe.request` and `app.modules.campaigns.service.create_call`). Nothing leaves the machine: a
socket guard refuses every outbound connection that is not to localhost.

Why: the shared full stack (:8000) runs with PRIVAT_ENABLED unset, so every /privat call answers 403 privat_not_enabled
(and the web silently falls back to its in-browser simulation). This harness gives Playwright a real Privat backend.

Run (from the repo root):
    source /home/claude/qa-env.sh
    QA_PRIV_DB=postgresql+psycopg://postgres:postgres@localhost:5432/qa_priv_stack python -m tests.qa.qa_privat_stack
and a second Next server from the existing build:
    cd web && API_BASE_URL=http://localhost:8100 PREVIEW_GATE=off npx next start -p 3100

Fake Stripe: POST /checkout/sessions returns a hosted page on this server (/__qa/stripe/pay/<id>) that asks ONLY for the
fields the session payload told Stripe to collect (name + address with billing_address_collection=required, phone with
phone_number_collection.enabled, e-mail from customer_email, card when payment_method_collection=always). Stripe's test
cards: 4242 4242 4242 4242 succeeds, 4000 0025 0000 3155 needs 3-D Secure (approve / fail), 4000 0000 0000 0002 is
declined, 4000 0000 0000 9995 has insufficient funds. A failed attempt leaves the session `open` with no subscription
(Checkout on API ≥ 2025-03-31 creates the subscription only after a completed payment). Success → session `complete`,
subscription `trialing` (trial_period_days) or `active`, a signed checkout.session.completed webhook, then the redirect to
success_url. Introspection: GET /__qa/stripe/sessions, GET/DELETE /__qa/calls (what would have been dialled).
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import socket
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

PORT = int(os.environ.get("QA_PRIV_PORT", "8100"))
FRONT = os.environ.get("QA_PRIV_FRONT", "http://localhost:3100")
WEBHOOK_SECRET = "whsec_qa_privat_stack"
DB = os.environ.get("QA_PRIV_DB", "postgresql+psycopg://postgres:postgres@localhost:5432/qa_priv_stack")

os.environ.update({
    "APP_ENV": "test", "ENABLE_DEV_TOOLS": "true", "EMAIL_ADAPTER": "simulated", "AI_PROVIDER": "fake",
    "TTS_ENGINE": "fake", "TELEPHONY_PROVIDER": "fake", "CONNECTORS_PROVIDER": "fake", "DATABASE_URL": DB,
    "FRONTEND_BASE_URL": FRONT, "PRIVAT_ENABLED": "true", "PRIVAT_ALLOWED_EMAILS": "",
    "STRIPE_SECRET_KEY": "sk_test_qa_fake_never_sent", "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
    "VAPI_API_KEY": "vapi-qa-fake-never-sent", "VAPI_SERVER_SECRET": "vapi-qa-secret",
    "PRIVAT_POOL_NUMBERS": "+4589870000=pn_pool", "PRIVAT_SHORT_URL_BASE": f"{FRONT}/i/",
    "PRIVAT_GROUP_URL_BASE": f"{FRONT}/g/",
})

# ----------------------------------------------------------------------------------------------- no network, ever
_real_connect = socket.socket.connect


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and host not in ("127.0.0.1", "localhost", "::1") and not host.startswith("/"):
        raise ConnectionRefusedError(f"qa_privat_stack: outbound connection to {host!r} blocked")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]

from alembic.config import Config  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.db import get_engine  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate() -> None:
    with get_engine().connect() as c:
        has = c.execute(text("select to_regclass('public.alembic_version')")).scalar()
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    command.upgrade(cfg, "head")
    print("qa_privat_stack: migrated" + (" (existing)" if has else " (fresh)"), flush=True)


# ----------------------------------------------------------------------------------------------- calling-hours clock
from app.modules.privat import rules  # noqa: E402

_real_now = rules.now
_OFFSET = timedelta(0)
if not rules.in_call_hours(_real_now()):  # run the harness outside 8–18 on a weekday: shift Privat's clock to Wed 10:00
    t = rules.local(_real_now())
    target = t.replace(hour=10, minute=0, second=0, microsecond=0)
    while target.weekday() != 2 or target <= t:
        target += timedelta(days=1)
    _OFFSET = target - t
rules.now = lambda: _real_now() + _OFFSET  # type: ignore[assignment]

# ----------------------------------------------------------------------------------------------- fake Stripe
from app.modules.billing import stripe as stripe_api  # noqa: E402

LOCK = threading.Lock()
SESSIONS: dict[str, dict] = {}
SUBS: dict[str, dict] = {}
TAX: dict[str, dict] = {}
LOG: list[tuple[str, str]] = []


def _session_obj(s: dict) -> dict:
    return {k: v for k, v in s.items() if not k.startswith("_")}


def fake_request(method: str, path: str, data: dict | None = None, **_k) -> dict:
    with LOCK:
        LOG.append((method, path))
        if path == "/tax_rates":
            if method == "GET":
                return {"data": list(TAX.values())}
            rid = f"txr_qa_{len(TAX) + 1}"
            TAX[rid] = {"id": rid, **(data or {})}
            return TAX[rid]
        if method == "POST" and path == "/checkout/sessions":
            sid = f"cs_test_qa_{uuid.uuid4().hex[:20]}"
            d = data or {}
            SESSIONS[sid] = {"id": sid, "object": "checkout.session", "mode": d.get("mode"), "status": "open",
                             "payment_status": "unpaid", "subscription": None, "customer": d.get("customer"),
                             "customer_email": d.get("customer_email"), "metadata": d.get("metadata") or {},
                             "client_reference_id": d.get("client_reference_id"), "customer_details": None,
                             "url": f"http://localhost:{PORT}/__qa/stripe/pay/{sid}", "_payload": d}
            return _session_obj(SESSIONS[sid])
        if method == "GET" and path.startswith("/checkout/sessions/"):
            s = SESSIONS.get(path.rsplit("/", 1)[1])
            if s is None:
                raise stripe_api.StripeFailed("Stripe afviste kaldet: No such checkout.session")
            return _session_obj(s)
        if method == "GET" and path.startswith("/subscriptions/"):
            sub = SUBS.get(path.rsplit("/", 1)[1])
            if sub is None:
                raise stripe_api.StripeFailed("Stripe afviste kaldet: No such subscription")
            return sub
        if method == "DELETE" and path.startswith("/subscriptions/"):  # cancel now (the duplicate guard, F-PK-01)
            sub = SUBS.get(path.rsplit("/", 1)[1])
            if sub is None:
                raise stripe_api.StripeFailed("Stripe afviste kaldet: No such subscription")
            sub.update(status="canceled", ended_at=int(rules.now().timestamp()))
            return sub
        if method == "POST" and path == "/billing_portal/sessions":
            return {"url": f"{FRONT}/privat/konto"}
    raise stripe_api.StripeFailed(f"qa fake Stripe: {method} {path} is not simulated")


stripe_api.request = fake_request  # type: ignore[assignment]

# ----------------------------------------------------------------------------------------------- fake Vapi
from app.modules.campaigns import service as campaigns  # noqa: E402

DIALLED: list[dict] = []


def fake_create_call(payload: dict) -> dict:
    with LOCK:
        DIALLED.append({"at": datetime.now(UTC).isoformat(), "payload": payload})
        # unique across restarts and DELETE /__qa/calls: the DB keeps private_calls.vapi_call_id (UNIQUE), so a counter
        # that starts again at 1 made «Godkend opkald» answer 500 UniqueViolation (PB, 2026-11-10)
        return {"id": f"qa_call_{len(DIALLED)}_{uuid.uuid4().hex[:8]}"}


campaigns.create_call = fake_create_call  # type: ignore[assignment]

# ----------------------------------------------------------------------------------------------- the app
from app.main import create_app  # noqa: E402

app = create_app()

CARDS = {"4242424242424242": "ok", "4000002500003155": "3ds", "4000000000000002": "declined",
         "4000000000009995": "insufficient_funds"}
ERRORS = {"declined": "Dit kort blev afvist.", "insufficient_funds": "Dit kort har ikke dækning nok.",
          "3ds_failed": "Godkendelsen af betalingen mislykkedes. Prøv et andet kort.",
          "missing": "Udfyld alle felter."}


def _fields(s: dict) -> list[tuple[str, str, str]]:
    p = s["_payload"]
    out = []
    if p.get("billing_address_collection") == "required":
        out += [("name", "Navn på kortholder", ""), ("line1", "Adresse", ""), ("postal_code", "Postnummer", ""),
                ("city", "By", "")]
    if (p.get("phone_number_collection") or {}).get("enabled"):
        out.append(("phone", "Telefon", ""))
    out.append(("email", "E-mail", s.get("customer_email") or ""))
    if p.get("payment_method_collection") == "always" or p.get("mode") == "payment":
        out.append(("card", "Kortnummer", ""))
    return out


def _page(s: dict, error: str | None = None) -> HTMLResponse:
    p = s["_payload"]
    trial = (p.get("subscription_data") or {}).get("trial_period_days")
    rows = "".join(f'<label>{html.escape(lbl)}<input name="{n}" aria-label="{html.escape(lbl)}" value="{html.escape(v)}"></label>'
                   for n, lbl, v in _fields(s))
    err = f'<p role="alert" data-testid="stripe-error">{html.escape(error)}</p>' if error else ""
    btn = f"Start {trial} dages prøveperiode" if trial else "Betal"
    body = (f'<!doctype html><html lang="da"><head><meta charset="utf-8"><title>Fake Stripe Checkout (QA)</title></head>'
            f'<body data-testid="fake-stripe"><a href="{html.escape(p.get("cancel_url") or "/")}">Tilbage</a>'
            f'<h1>Fake Stripe Checkout (QA)</h1><p data-testid="trial-days">{trial or 0}</p>{err}'
            f'<form method="post">{rows}<button type="submit">{btn}</button></form></body></html>')
    return HTMLResponse(body)


def _webhook(event: dict) -> None:
    import httpx

    body = json.dumps(event).encode()
    ts = int(time.time())
    sig = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    try:
        httpx.post(f"http://127.0.0.1:{PORT}/api/v1/webhooks/stripe", content=body,
                   headers={"stripe-signature": f"t={ts},v1={sig}", "content-type": "application/json"}, timeout=10)
    except Exception as e:  # noqa: BLE001
        print("qa_privat_stack: webhook failed", e, flush=True)


def _complete(s: dict) -> str:
    p = s["_payload"]
    sd = p.get("subscription_data") or {}
    trial = sd.get("trial_period_days")
    now = rules.now()
    cust = s.get("customer") or f"cus_qa_{uuid.uuid4().hex[:12]}"
    sub_id = f"sub_qa_{uuid.uuid4().hex[:12]}"
    interval = ((p.get("line_items") or [{}])[0].get("price_data") or {}).get("recurring", {}).get("interval") \
        or (sd.get("metadata") or {}).get("interval") or "month"
    end = now + (timedelta(days=int(trial)) if trial else timedelta(days=30 if interval == "month" else 365))
    if p.get("mode") == "subscription":
        SUBS[sub_id] = {"id": sub_id, "object": "subscription", "status": "trialing" if trial else "active",
                        "customer": cust, "cancel_at_period_end": False, "currency": "dkk",
                        "trial_end": int(end.timestamp()) if trial else None, "metadata": sd.get("metadata") or {},
                        "items": {"data": [{"current_period_end": int(end.timestamp()),
                                            "price": {"recurring": {"interval": interval}}}]}}
        s["subscription"] = sub_id
    s.update(status="complete", customer=cust, payment_status="no_payment_required" if trial else "paid")
    if p.get("mode") == "payment":  # real Stripe always reports what was paid; the top-up webhook checks it
        items = p.get("line_items") or []
        s["amount_total"] = sum(int((li.get("price_data") or {}).get("unit_amount") or 0) * int(li.get("quantity") or 1)
                                for li in items)
        s.setdefault("currency", ((items[0].get("price_data") or {}).get("currency") if items else None) or "dkk")
    threading.Thread(target=_webhook, args=({"id": f"evt_qa_{uuid.uuid4().hex[:16]}", "type": "checkout.session.completed",
                                             "data": {"object": _session_obj(s)}},), daemon=True).start()
    return (p.get("success_url") or "/").replace("{CHECKOUT_SESSION_ID}", s["id"])


@app.get("/__qa/stripe/pay/{sid}", include_in_schema=False)
def qa_pay_page(sid: str):
    s = SESSIONS.get(sid)
    if s is None:
        return HTMLResponse("unknown session", status_code=404)
    if s["status"] != "open":
        return HTMLResponse("Denne betaling er afsluttet.", status_code=410)
    return _page(s)


@app.post("/__qa/stripe/pay/{sid}", include_in_schema=False)
async def qa_pay_submit(sid: str, request: Request):
    s = SESSIONS.get(sid)
    if s is None or s["status"] != "open":
        return HTMLResponse("unknown or closed session", status_code=410)
    form = {k: v[0].strip() for k, v in parse_qs((await request.body()).decode()).items()}
    with LOCK:
        s.setdefault("_attempts", []).append({k: ("****" + v[-4:] if k == "card" else v) for k, v in form.items()})
        if any(not form.get(n) for n, _l, _v in _fields(s)):
            return _page(s, ERRORS["missing"])
        s["customer_details"] = {"name": form.get("name"), "email": form.get("email"), "phone": form.get("phone"),
                                 "address": {"line1": form.get("line1"), "postal_code": form.get("postal_code"),
                                             "city": form.get("city"), "country": "DK"}}
        outcome = CARDS.get(form.get("card", "").replace(" ", ""), "declined")
        if outcome == "3ds":
            return HTMLResponse(f'<!doctype html><html lang="da"><body data-testid="fake-3ds"><h1>3-D Secure</h1>'
                                f'<a href="/__qa/stripe/3ds/{sid}?ok=1">Godkend</a> <a href="/__qa/stripe/3ds/{sid}?ok=0">Afvis</a>'
                                f'</body></html>')
        if outcome != "ok":
            return _page(s, ERRORS[outcome])
        url = _complete(s)
    return RedirectResponse(url, status_code=303)


@app.get("/__qa/stripe/3ds/{sid}", include_in_schema=False)
def qa_3ds(sid: str, ok: int = 0):
    s = SESSIONS.get(sid)
    if s is None or s["status"] != "open":
        return HTMLResponse("unknown or closed session", status_code=410)
    with LOCK:
        if not ok:
            return _page(s, ERRORS["3ds_failed"])
        url = _complete(s)
    return RedirectResponse(url, status_code=303)


@app.get("/__qa/stripe/sessions", include_in_schema=False)
def qa_sessions():
    return JSONResponse({"sessions": [{**_session_obj(s), "payload": s["_payload"], "attempts": s.get("_attempts", [])}
                                      for s in SESSIONS.values()], "subscriptions": list(SUBS.values()), "log": LOG})


@app.get("/__qa/calls", include_in_schema=False)
def qa_calls():
    return {"dialled": DIALLED}


@app.post("/__qa/phone-verified", include_in_schema=False)
async def qa_phone_verified(request: Request):
    """Test shortcut (like tests/privat_fixtures.Pv.verify_phone): mark a user's own mobile number as verified."""
    from app.db import get_session_factory
    from app.models import PrivateProfile, User

    body = await request.json()
    with get_session_factory()() as db:
        u = db.query(User).filter_by(email_normalized=str(body["email"]).lower()).one()
        p = db.query(PrivateProfile).filter_by(user_id=u.id).one()
        p.phone_e164, p.phone_verified_at = body.get("phone") or "+4520304050", rules.now()
        db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------------------------- worker
def _worker() -> None:
    from app.worker import runner

    while True:
        try:
            runner.drain(200)
        except Exception as e:  # noqa: BLE001
            print("qa_privat_stack: worker error", repr(e)[:300], flush=True)
        time.sleep(1.0)


if __name__ == "__main__":
    import uvicorn

    migrate()
    threading.Thread(target=_worker, daemon=True).start()
    print(f"qa_privat_stack: http://localhost:{PORT} (clock offset {_OFFSET})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
