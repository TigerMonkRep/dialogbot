"""Reproducible stage-1 journey against a RUNNING API and worker.

    uvicorn app.main:app --port 8000          # terminal 1
    python -m app.worker.runner               # terminal 2
    python -m client.demo_flow                # terminal 3

Requires ENABLE_DEV_TOOLS=true (simulated mailbox). Nothing here uses a real
mail, phone, calendar or payment provider; every "not implemented" answer from
the API is printed as such.

Journey (blueprint §9.1 restricted to stage 1):
  konto → verificering → arbejdsrum → virksomhedsprofil → kategorier → mål/sprog →
  manuel viden → godkendelse → opsætningsplan → invitation af kollega →
  log ud / log ind → genoptag ved næste trin → forsøg på aktivering (ærligt afvist)
"""
from __future__ import annotations

import os
import re
import sys
import uuid

from client.dialogbot_client import ApiError, DialogbotClient

BASE = os.environ.get("DIALOGBOT_BASE_URL", "http://localhost:8000")
PASSWORD = "Demo-Password!2026"


def step(title: str) -> None:
    print(f"\n== {title}")


def link(mail: dict, pattern: str) -> str:
    m = re.search(pattern, mail["body_text"])
    assert m, mail["body_text"]
    return m.group(1)


def main() -> int:
    run = uuid.uuid4().hex[:6]
    owner_mail = f"ejer-{run}@demo-dialogbot.dk"
    colleague_mail = f"kollega-{run}@demo-dialogbot.dk"
    owner = DialogbotClient(BASE)
    print("ready:", owner.ready())

    step("A01/A02/A03 – konto, login, e-mailbekræftelse via simuleret postkasse")
    owner.register(owner_mail, PASSWORD, "Mads Fjord", signup_intent="both")
    owner.login(owner_mail, PASSWORD)
    print("verified before:", owner.me()["email_verified"])
    mail = owner.wait_for_mail("Bekræft")
    owner.verify_email(link(mail, r"token=([A-Za-z0-9_\-]+)"))
    print("verified after:", owner.me()["email_verified"])

    step("A06 – arbejdsrum med bevaret produktintention")
    ws = owner.create_workspace(f"Fjord Gulvservice ApS ({run})")["id"]
    print("workspace:", ws, "intent:", owner.list_workspaces()[0]["product_intent"])

    step("O01/S01 – virksomhedsprofil uden hjemmeside, flere kategorier inkl. egen")
    owner.update_profile(ws, description="Professionel gulvafslibning, lakering og rådgivning", city="København",
                         postal_code="2100", manual_setup=True, website_url=None)
    owner.add_category(ws, "Håndværk & Gulvservice", slug="haandvaerk-gulvservice", is_primary=True)
    owner.add_category(ws, "Poolservice og vedligeholdelse")  # custom
    print("categories:", [c["label"] for c in owner._req("GET", f"/workspaces/{ws}/categories")])

    step("O03/O04 – mål, kapabiliteter og fire sprogniveauer")
    owner.update_goals(ws, product_intent="both", inbound_phone=True, callback=True, booking=True,
                       conversation_goals=["tilbud på afslibning", "book besigtigelse"])
    owner.update_languages(ws, enabled_conversation_languages=["da", "en"], report_language="da")

    step("K03/K01 – manuel viden: ydelse, åbningstider, K04-tilbud (>= 40 m²)")
    svc = owner.create_knowledge(ws, "service", "Standard gulvafslibning inkl. 2x klar lak",
                                 {"unit": "m2", "price_net_minor": 14500, "currency": "DKK"})
    hours = owner.create_knowledge(ws, "opening_hours", "Telefontider",
                                   {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": "07:30",
                                                "close": "16:00"}]})
    offer = owner.create_knowledge(ws, "offer", "Efterårsrabat på gulvafslibning",
                                   {"discount_percent": 15, "condition": {"area_operator": "gte",
                                                                          "area_threshold_m2": 40},
                                    "starts_on": "2026-10-01", "ends_on_inclusive": "2026-11-30"})
    print("assistant sees before approval:", len(owner.assistant_knowledge(ws)["items"]), "items")

    step("K05 – godkendelse (kladde → gennemgang → godkendt), idempotent")
    for it in (svc, hours, offer):
        vid = it["open_draft"]["id"]
        owner.submit(ws, vid)
        key = f"approve-{vid}"
        owner.approve(ws, vid, idempotency_key=key)
        owner.approve(ws, vid, idempotency_key=key)  # replay → same answer, no second revision
    active = owner.assistant_knowledge(ws)
    print("assistant sees after approval:", len(active["items"]), "items, revision", active["knowledge_revision"])
    for area in (39, 40, 41):
        print(f"  offer eligibility {area} m² on 2026-10-28:",
              owner.offer_eligibility(ws, offer["id"], area, "2026-10-28")["eligible"])
    print("  offer eligibility 65 m² on 2026-12-01:", owner.offer_eligibility(ws, offer["id"], 65, "2026-12-01")["eligible"])

    step("G05 – kør servertjek; ikke-implementerede tjek springes ærligt over")
    res = owner.run_all_checks(ws)
    print("results:", {r["check_key"]: r["status"] for r in res["results"]})
    print("skipped:", [s["check_key"] for s in res["skipped"]])
    try:
        owner.run_check(ws, "calendar.connection")
    except ApiError as e:
        print("calendar check:", e.status, e.code, "-", e.body["message"])

    step("G01/G02 – personlig plan")
    plan = owner.plan(ws)
    print(f"progress: {plan['progress']['required_complete']}/{plan['progress']['required_total']} "
          f"({plan['progress']['percent']} %)")
    for t in plan["tasks"]:
        flag = "!" if t["required"] else " "
        blocked = f" ← {t['blocked_by'][0]['message'][:70]}" if t["blocked_by"] else ""
        print(f"  {flag} {t['key']:<32} {t['status']:<14}{blocked}")
    print("next:", plan["next_action"]["key"] if plan["next_action"] else None, "|", plan["next_action_explanation"])

    step("S02/A05 – invitér kollega (staff) og acceptér via simuleret mail")
    owner.invite(ws, colleague_mail, "staff", idempotency_key=f"inv-{run}")
    owner.invite(ws, colleague_mail, "staff", idempotency_key=f"inv-{run}")  # replayed, no duplicate
    colleague = DialogbotClient(BASE)
    colleague.register(colleague_mail, PASSWORD, "Jonas Bech")
    colleague.login(colleague_mail, PASSWORD)
    colleague.verify_email(link(colleague.wait_for_mail("Bekræft"), r"token=([A-Za-z0-9_\-]+)"))
    inv_token = link(colleague.wait_for_mail("inviteret"), r"invite/([A-Za-z0-9_\-]+)")
    print("preview:", colleague.invitation_preview(inv_token))
    print("accepted:", colleague.accept_invitation(inv_token)["role"])
    try:
        colleague.accept_invitation(inv_token)
    except ApiError as e:
        print("second acceptance:", e.status, e.code)
    draft = colleague.create_knowledge(ws, "fact", "Parkering", {"text": "Gratis parkering i gården"})
    colleague.submit(ws, draft["open_draft"]["id"])
    try:
        colleague.approve(ws, draft["open_draft"]["id"])
    except ApiError as e:
        print("staff approve:", e.status, e.code)
    print("staff sees review task as:", colleague.task(ws, "knowledge.review")["status"])

    step("G01 – gem/genoptag: ny session åbner samme næste trin")
    before = owner.plan(ws)["next_action"]
    owner.logout()
    owner.login(owner_mail, PASSWORD)
    after = owner.plan(ws)
    print("next before:", before["key"] if before else None, "| after:", after["next_action"]["key"] if after["next_action"] else None,
          "| open drafts/in review:", after["resume"])
    owner.approve(ws, draft["open_draft"]["id"])
    print("after approval, review task:", owner.task(ws, "knowledge.review")["status"])

    step("G06 – aktivering er en særskilt kommando og afvises ærligt")
    for cmd in ("reception", "campaigns"):
        try:
            owner._req("POST", f"/workspaces/{ws}/setup/activate/{cmd}")
        except ApiError as e:
            print(f"activate {cmd}:", e.status, e.code, "-", e.body["message"][:90])

    step("S09 – seneste audit")
    for a in owner.audit(ws, limit=8)["items"]:
        print(f"  {a['created_at'][11:19]} {a['action']:<28} {a['object_type']}")
    print("\nDone. Workspace id:", ws)
    return 0


if __name__ == "__main__":
    sys.exit(main())
