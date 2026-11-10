"""QA X22 (api-contract-qa, bølge 2 / M2): Public API v1 – nøgler, scopes, rate limit, paginering, webhook-signatur,
svar matcher docs/public-openapi.json.

Supplerer tests/test_public_api.py (som allerede dækker nøgle-udstedelse, 401/403/404, maskering, idempotens,
rate limit og signeret levering). Her: kontrakt mod den committede OpenAPI-fil for HVERT endpoint (200 og fejl),
fuzz af parametre (ingen 500), paginering af beskeder, webhook-data vs. scopes, nøgle-livscyklus.

Kør: TEST_DATABASE_URL=…/qa_p1misc pytest -p no:cacheprovider tests/qa/test_qa_X22.py
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from jsonschema import Draft202012Validator

from app.models import ApiKey, Conversation, ConversationMessage, DailyReport
from app.modules.public_api import scopes
from app.worker import runner
from tests.test_public_api import (  # noqa: F401  (fixtures)
    HOOK,
    V1,
    _booking_setup,
    _fresh_limiter,
    _hook,
    _issue,
    _phone_call,
    keyed,
    ph,
    receiver,
    telephony,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC = json.load(open(os.path.join(ROOT, "docs", "public-openapi.json"), encoding="utf-8"))
EVIDENCE = os.path.join(ROOT, "qa", "evidence", "X22")


def _validator(path: str, method: str, status: str):
    op = SPEC["paths"][path][method]
    resp = op["responses"].get(status)
    if resp is None:
        return None
    schema = resp.get("content", {}).get("application/json", {}).get("schema")
    if schema is None:
        return None
    root = {**schema, "components": SPEC["components"]}
    return Draft202012Validator(root)


def _errors(path, method, status, body) -> list[str]:
    v = _validator(path, method, status)
    if v is None:
        return [f"{method.upper()} {path}: status {status} er ikke dokumenteret i docs/public-openapi.json"]
    return [f"{method.upper()} {path} {status}: {e.json_path}: {e.message}" for e in v.iter_errors(body)]


def _seed_everything(api, t, db):
    """One of every resource in workspace A, through the app's own paths."""
    tok, ws = t["tok_a"], t["ws_a"]
    _phone_call(api, t)
    type_id = _booking_setup(api, t)
    slot = api.get(tok, f"/workspaces/{ws}/bookings/slots?type_id={type_id}").json()["items"][0]
    b = api.post(tok, f"/workspaces/{ws}/bookings", {"type_id": type_id, "start": slot["start"], "name": "Mette",
                                                     "phone": "+4520304050", "email": "mette@example.dk"}).json()
    from app.modules.campaigns import service as campaigns

    api.post(tok, f"/workspaces/{ws}/campaigns", {"name": "Forårstilbud", "purpose": "Gulvafslibning",
                                                   "call_days": list(campaigns.DAYS), "call_from": "09:00", "call_to": "17:00"})
    api.c.post(f"{V1}/workspaces/{ws}/do-not-call", json={"phone": "21222324"},
               headers=ph(t["key_a"], **{"Idempotency-Key": "seed-dnc"}))
    db.add(DailyReport(workspace_id=uuid.UUID(ws), report_date=date(2026, 9, 24), timezone="Europe/Copenhagen",
                       data={"conversations": {"started": 3, "visitor_messages": 7}, "leads": {"new": 2, "approved": 1,
                             "rejected": 0}, "tasks": {"created": 1, "completed": 0, "open_overdue_at_end": 2}}))
    db.commit()
    return {"booking_id": b["id"], "type_id": type_id}


# --------------------------------------------------------------------------- contract: committed file == code

def test_committed_openapi_equals_the_code():
    from app.modules.public_api.app import create_public_app

    live = create_public_app().openapi()
    live["servers"] = SPEC["servers"]  # base URL comes from env
    assert live == SPEC, "docs/public-openapi.json er ude af trit med koden"


# --------------------------------------------------------------------------- contract: every 2xx body matches the file

def test_every_success_response_matches_the_openapi_schema(api, keyed, telephony, receiver, db):  # noqa: F811
    t = keyed
    ids = _seed_everything(api, t, db)
    ws = t["ws_a"]
    base = f"{V1}/workspaces/{ws}"
    k = ph(t["key_a"])
    hook = _hook(api, t, key="contract-hook")
    assert hook.status_code == 201
    problems = _errors("/workspaces/{workspace_id}/webhooks", "post", "201", hook.json())
    api.post(t["tok_a"], f"/workspaces/{ws}/leads", {"contact_name": "Ole", "need_summary": "Tilbud"})  # → a delivery
    runner.drain()
    call = api.c.get(f"{base}/calls", headers=k).json()["items"][0]
    conv = api.c.get(f"{base}/conversations", headers=k).json()["items"][0]
    lead = api.c.get(f"{base}/leads", headers=k).json()["items"][0]
    kn = api.c.get(f"{base}/knowledge", headers=k).json()["items"][0]
    w = hook.json()["id"]
    gets = {
        "/me": f"{V1}/me",
        "/workspaces/{workspace_id}/calls": f"{base}/calls",
        "/workspaces/{workspace_id}/calls/{call_id}": f"{base}/calls/{call['id']}",
        "/workspaces/{workspace_id}/conversations": f"{base}/conversations",
        "/workspaces/{workspace_id}/conversations/{conversation_id}": f"{base}/conversations/{conv['id']}",
        "/workspaces/{workspace_id}/conversations/{conversation_id}/messages": f"{base}/conversations/{conv['id']}/messages",
        "/workspaces/{workspace_id}/booking-types": f"{base}/booking-types",
        "/workspaces/{workspace_id}/bookings": f"{base}/bookings",
        "/workspaces/{workspace_id}/bookings/{booking_id}": f"{base}/bookings/{ids['booking_id']}",
        "/workspaces/{workspace_id}/leads": f"{base}/leads",
        "/workspaces/{workspace_id}/leads/{lead_id}": f"{base}/leads/{lead['id']}",
        "/workspaces/{workspace_id}/knowledge": f"{base}/knowledge",
        "/workspaces/{workspace_id}/knowledge/{item_id}": f"{base}/knowledge/{kn['item_id']}",
        "/workspaces/{workspace_id}/campaigns": f"{base}/campaigns",
        "/workspaces/{workspace_id}/do-not-call": f"{base}/do-not-call",
        "/workspaces/{workspace_id}/reports/daily": f"{base}/reports/daily?from=2026-09-01&to=2026-09-30",
        "/workspaces/{workspace_id}/reports/daily/{report_date}": f"{base}/reports/daily/2026-09-24",
        "/workspaces/{workspace_id}/webhooks": f"{base}/webhooks",
        "/workspaces/{workspace_id}/webhooks/events": f"{base}/webhooks/events",
        "/workspaces/{workspace_id}/webhooks/{endpoint_id}": f"{base}/webhooks/{w}",
        "/workspaces/{workspace_id}/webhooks/{endpoint_id}/deliveries": f"{base}/webhooks/{w}/deliveries",
    }
    assert set(gets) | {"/workspaces/{workspace_id}/do-not-call"} >= {p for p, ops in SPEC["paths"].items() if "get" in ops}
    for path, url in gets.items():
        r = api.c.get(url, headers=k)
        assert r.status_code == 200, (url, r.text)
        body = r.json()
        if "items" in body and isinstance(body["items"], list) and path not in ("/workspaces/{workspace_id}/webhooks/events",):
            assert body["items"], f"{url} gav en tom liste – seed mangler, kontrakten testes ikke"
        problems += _errors(path, "get", "200", body)
    r = api.c.post(f"{base}/do-not-call", json={"phone": "21222399"}, headers=ph(t["key_a"], **{"Idempotency-Key": "c-dnc"}))
    problems += _errors("/workspaces/{workspace_id}/do-not-call", "post", "201", r.json())
    r = api.c.patch(f"{base}/webhooks/{w}", json={"events": ["lead.created"]}, headers=k)
    problems += _errors("/workspaces/{workspace_id}/webhooks/{endpoint_id}", "patch", "200", r.json())
    assert api.c.delete(f"{base}/webhooks/{w}", headers=k).status_code == 204
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- contract: error answers

@pytest.mark.xfail(strict=True, reason="F-M2-09-X22: S2 new – OpenAPI-kontrakten (docs/public-openapi.json) dokumenterer ingen fejlsvar ud over 422 – og 422 er …")
def test_error_answers_are_documented_and_match_the_documented_shape(api, keyed):  # noqa: F811
    """docs/public-api.md lister 401/403/404/409/422/429 med konvolutten {code,message,field_errors,request_id}.
    OpenAPI-filen er «kontrakten» (public-api.md §Versionering) – en genereret klient skal kunne parse fejlene."""
    t = keyed
    base = f"{V1}/workspaces/{t['ws_a']}"
    limited = _issue(api, t["tok_a"], t["ws_a"], ["calls:read"])["key"]
    cases = [
        ("/workspaces/{workspace_id}/calls", "get", api.c.get(f"{base}/calls?limit=0", headers=ph(t["key_a"]))),
        ("/workspaces/{workspace_id}/calls", "get", api.c.get(f"{base}/calls", headers=ph("dbk_live_" + "x" * 43))),
        ("/workspaces/{workspace_id}/leads", "get", api.c.get(f"{base}/leads", headers=ph(limited))),
        ("/workspaces/{workspace_id}/calls/{call_id}", "get", api.c.get(f"{base}/calls/{uuid.uuid4()}", headers=ph(t["key_a"]))),
    ]
    problems, seen = [], []
    v422 = SPEC["components"]["schemas"].get("HTTPValidationError", {})
    if "code" not in v422.get("properties", {}):
        problems.append("422 er dokumenteret som FastAPI HTTPValidationError {detail:[…]}, men svaret er "
                        "{code,message,field_errors,request_id} – ingen af de faktiske felter står i skemaet")
    for path, method, r in cases:
        body = r.json()
        seen.append({"path": path, "status": r.status_code, "body": body})
        assert {"code", "message", "field_errors", "request_id"} <= set(body), body  # the envelope itself is consistent
        problems += _errors(path, method, str(r.status_code), body)
    os.makedirs(EVIDENCE, exist_ok=True)
    with open(os.path.join(EVIDENCE, "error-responses.json"), "w", encoding="utf-8") as f:
        json.dump({"observed": seen, "problems": problems}, f, ensure_ascii=False, indent=1)
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- robustness: no 500 for odd input

ODD = ["", "%00", "x" * 5000, "ÆØÅ😀", "-1", "1e9", "null", "[]", "{}", "' or 1=1--", "2026-13-45", "../..",
       "MjAyNi0wMS0wMVQwMDowMDowMHw" + "x" * 10]


def _b64(s: str) -> str:
    import base64

    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_no_500_for_odd_query_values_and_crafted_cursors(api, keyed, telephony, receiver, db):  # noqa: F811
    t = keyed
    _seed_everything(api, t, db)
    base = f"{V1}/workspaces/{t['ws_a']}"
    k = ph(t["key_a"])
    cursors = ODD + [_b64("2026-01-01T00:00:00|" + str(uuid.uuid4())),  # naive timestamp
                     _b64("9999-12-31T23:59:59+14:00|" + str(uuid.uuid4())),
                     _b64("0001-01-01T00:00:00+00:00|" + str(uuid.uuid4())),
                     _b64("2026-01-01T00:00:00+00:00|not-a-uuid"), _b64("|"), _b64("x" * 300)]
    params = {"calls": ["since", "until", "direction"], "conversations": ["channel", "status"],
              "bookings": ["from", "to", "status"], "leads": ["since", "pipeline_status", "qualification_status"],
              "campaigns": ["status"], "do-not-call": [], "booking-types": ["include_inactive"],
              "knowledge": ["kind"], "reports/daily": ["from", "to", "limit"]}
    bad = []
    for res, names in params.items():
        for c in cursors:
            r = api.c.get(f"{base}/{res}", params={"cursor": c, "limit": 2}, headers=k)
            if r.status_code >= 500 or "code" not in r.json() and r.status_code != 200:
                bad.append((res, "cursor", c[:40], r.status_code, r.text[:120]))
        for name in names + ["limit"]:
            for v in ODD:
                r = api.c.get(f"{base}/{res}", params={name: v}, headers=k)
                if r.status_code >= 500 or (r.status_code != 200 and "code" not in r.json()):
                    bad.append((res, name, v[:40], r.status_code, r.text[:120]))
    for v in ODD:
        for path in (f"{base}/calls/{v}", f"{base}/reports/daily/{v}", f"{V1}/workspaces/{v}/calls"):
            r = api.c.get(path, headers=k)
            if r.status_code >= 500:
                bad.append((path[:60], "path", v[:40], r.status_code, r.text[:120]))
    # odd bodies on the two writes
    for body in ({}, {"phone": None}, {"phone": "x" * 10000}, {"phone": 4520304050}, [], {"url": HOOK, "events": "lead.created"},
                 {"url": "javascript:alert(1)", "events": ["lead.created"]}, {"url": HOOK, "events": [], "description": "x" * 100000}):
        for i, path in enumerate((f"{base}/do-not-call", f"{base}/webhooks")):
            r = api.c.post(path, json=body, headers=ph(t["key_a"], **{"Idempotency-Key": f"odd-{i}-{uuid.uuid4()}"}))
            if r.status_code >= 500:
                bad.append((path[-12:], "body", str(body)[:40], r.status_code, r.text[:120]))
    assert not bad, "\n".join(map(str, bad))


# --------------------------------------------------------------------------- pagination

@pytest.mark.xfail(strict=True, reason="F-M2-10-X22: S2 new – GET /v1/…/conversations/{id}/messages afkorter stille ved `limit` (standard 200, maks 500) og svarer …")
def test_message_list_never_says_last_page_when_it_truncated(api, keyed, db):  # noqa: F811
    """public-api.md §Pagination: `next_cursor: null` = sidste side. /messages svarer altid null, men skærer ved
    limit (standard 200, maks 500) – en lang samtale bliver stille afkortet."""
    t = keyed
    ws = uuid.UUID(t["ws_a"])
    conv = Conversation(workspace_id=ws, channel="webchat", origin="web", visitor_token_digest=uuid.uuid4().hex)
    db.add(conv)
    db.flush()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    for i in range(205):
        db.add(ConversationMessage(conversation_id=conv.id, workspace_id=ws, role="visitor" if i % 2 else "assistant",
                                   text=f"besked {i}", created_at=start + timedelta(seconds=i)))
    db.commit()
    r = api.c.get(f"{V1}/workspaces/{t['ws_a']}/conversations/{conv.id}/messages", headers=ph(t["key_a"])).json()
    got = len(r["items"])
    assert got == 205 or r["next_cursor"] is not None, \
        f"fik {got} af 205 beskeder og next_cursor={r['next_cursor']!r} – klienten tror, samtalen er komplet"


def test_cursor_is_stable_with_identical_timestamps(api, keyed, db):  # noqa: F811
    """Keyset (created_at, id): rækker med samme tidsstempel må hverken gentages eller tabes over sidegrænser."""
    from app.models import Call

    t = keyed
    ws = uuid.UUID(t["ws_a"])
    same = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    made = set()
    for i in range(9):
        c = Call(workspace_id=ws, provider="vapi", provider_call_id=f"same{i}", summary=f"s{i}", created_at=same)
        db.add(c)
        db.flush()
        made.add(str(c.id))
    db.commit()
    seen, cur = [], None
    for _ in range(10):
        q = f"{V1}/workspaces/{t['ws_a']}/calls?limit=2" + (f"&cursor={cur}" if cur else "")
        page = api.c.get(q, headers=ph(t["key_a"])).json()
        seen += [x["id"] for x in page["items"]]
        cur = page["next_cursor"]
        if not cur:
            break
    assert len(seen) == len(set(seen)) == 9 and set(seen) == made


# --------------------------------------------------------------------------- webhooks vs. scopes / key lifecycle

@pytest.mark.xfail(strict=True, reason="F-M2-07-X22: S2 new – En nøgle med kun `webhooks:manage` kan abonnere på lead.created/booking.*/call.completed og få …")
def test_webhook_payload_respects_the_contacts_scope(api, keyed, receiver, db):  # noqa: F811
    """public-api.md §GDPR: «Telefonnumre og e-mails er maskeret uden contacts:read». En nøgle med KUN
    webhooks:manage kan abonnere på lead.created og få kontaktdata i klartekst – scope-modellen omgås."""
    t = keyed
    seen, _ = receiver
    only_hooks = _issue(api, t["tok_a"], t["ws_a"], ["webhooks:manage"])["key"]
    # the key can neither read leads nor see contacts through the read API
    assert api.c.get(f"{V1}/workspaces/{t['ws_a']}/leads", headers=ph(only_hooks)).status_code == 403
    r = api.c.post(f"{V1}/workspaces/{t['ws_a']}/webhooks", json={"url": HOOK, "events": ["lead.created"]},
                   headers=ph(only_hooks, **{"Idempotency-Key": "scope-bypass"}))
    assert r.status_code == 201, r.text
    api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/leads", {"contact_name": "Mette Hansen", "contact_phone": "+4520304050",
                                                          "contact_email": "mette@example.dk", "need_summary": "Tilbud"})
    runner.drain()
    assert seen, "ingen levering"
    body = json.loads(seen[-1].content)
    os.makedirs(EVIDENCE, exist_ok=True)
    with open(os.path.join(EVIDENCE, "webhook-lead-created-only-webhooks-scope.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=1)
    flat = json.dumps(body, ensure_ascii=False)
    assert "+4520304050" not in flat and "mette@example.dk" not in flat, \
        "nøgle uden contacts:read/leads:read modtager kontaktdata i klartekst via webhook"


@pytest.mark.xfail(strict=True, reason="F-M2-08-X22: S2 new – Webhook-endpoints oprettet med en nøgle bliver ved med at modtage data, efter nøglen er tilbagekaldt – og …")
def test_revoked_key_its_webhooks_are_visible_or_stopped(api, keyed, receiver, db):  # noqa: F811
    """Tilbagekaldelse «virker øjeblikkeligt». Endpoints oprettet af en nøgle bliver ved med at modtage data efter
    tilbagekaldelsen, og ejeren kan ikke se/slette dem i appen (ingen intern rute, ingen UI) – kun med en ny nøgle."""
    t = keyed
    seen, _ = receiver
    created = _issue(api, t["tok_b"], t["ws_b"], ["webhooks:manage"])
    r = api.c.post(f"{V1}/workspaces/{t['ws_b']}/webhooks", json={"url": HOOK, "events": ["lead.created"]},
                   headers=ph(created["key"], **{"Idempotency-Key": "rk"}))
    assert r.status_code == 201
    assert api.delete(t["tok_b"], f"/workspaces/{t['ws_b']}/api-keys/{created['id']}").status_code == 204
    assert api.c.get(f"{V1}/me", headers=ph(created["key"])).status_code == 401
    api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/leads", {"contact_name": "Ole", "contact_phone": "+4520304051",
                                                          "need_summary": "x"})
    runner.drain()
    internal = [api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/{p}").status_code
                for p in ("webhooks", "webhook-endpoints", "api-webhooks", "integrations/webhooks")]
    assert not seen or 200 in internal, \
        f"{len(seen)} levering(er) efter tilbagekaldelse, og ingen intern rute viser endpointet ({internal})"


@pytest.mark.xfail(strict=True, reason="F-M2-11-X22: S3 new – En udløbet API-nøgle tæller stadig med i grænsen på 2 aktive nøgler; rotation kræver, at man først …")
def test_expired_key_does_not_block_rotation(api, two_workspaces, db):
    """Højst 2 *aktive* nøgler (public-api.md). En udløbet nøgle er ikke aktiv (public_view → «expired»), men tæller
    stadig med i grænsen (keys.active_count tæller kun revoked_at IS NULL)."""
    t = two_workspaces
    a = _issue(api, t["tok_a"], t["ws_a"], ["calls:read"], expires_in_days=1)
    _issue(api, t["tok_a"], t["ws_a"], ["calls:read"])
    row = db.get(ApiKey, uuid.UUID(a["id"]))
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    listed = {k["id"]: k["status"] for k in api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/api-keys").json()}
    assert listed[a["id"]] == "expired"
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/api-keys", {"name": "ny", "scopes": ["calls:read"]})
    assert r.status_code == 201, f"{r.status_code} {r.json().get('code')}: udløbet nøgle blokerer en ny"


def test_staff_and_reader_cannot_issue_or_list_keys_and_scope_ceiling_holds(api, two_workspaces):
    t = two_workspaces
    staff = api.add_member(t["tok_a"], t["ws_a"], "staff-x22@testmail.dk", "staff")
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader-x22@testmail.dk", "reader")
    for tok in (staff, reader):
        assert api.get(tok, f"/workspaces/{t['ws_a']}/api-keys").status_code == 403
        assert api.post(tok, f"/workspaces/{t['ws_a']}/api-keys", {"name": "x", "scopes": ["calls:read"]}).status_code == 403
    admin = api.add_member(t["tok_a"], t["ws_a"], "admin-x22@testmail.dk", "admin")
    r = api.post(admin, f"/workspaces/{t['ws_a']}/api-keys", {"name": "x", "scopes": list(scopes.BUSINESS_SCOPES)})
    assert r.status_code in (201, 422), r.text  # admin may hold everything or get scope_not_allowed – never 500
    # cross-tenant: B's owner cannot list or revoke A's keys
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}/api-keys").status_code == 404
    if r.status_code == 201:
        assert api.delete(t["tok_b"], f"/workspaces/{t['ws_b']}/api-keys/{r.json()['id']}").status_code == 404


def test_the_app_has_a_place_to_issue_and_revoke_keys():
    """OpenAPI-beskrivelsen og public-api.md: «API-nøgle fra Integrationer → API-nøgler i appen». Der findes ingen
    side/komponent i web/src, der kalder /api-keys – kunden kan ikke få (eller tilbagekalde) en nøgle i produktet."""
    hits = []
    for dirpath, _d, files in os.walk(os.path.join(ROOT, "web", "src")):
        for f in files:
            if f.endswith((".ts", ".tsx")):
                txt = open(os.path.join(dirpath, f), encoding="utf-8").read()
                if "api-keys" in txt:
                    hits.append(os.path.join(dirpath, f))
    assert hits, "ingen UI kalder /workspaces/{id}/api-keys eller /privat/api-keys"
