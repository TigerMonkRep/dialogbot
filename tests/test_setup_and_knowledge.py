"""Acceptance 4–8: manual setup, resume, approved knowledge, goal-dependent plan, check staleness."""
from __future__ import annotations

from datetime import date

from app.modules.knowledge.service import offer_is_eligible


def _task(plan: dict, key: str) -> dict:
    return next(t for t in plan["tasks"] if t["key"] == key)


def _check(plan: dict, key: str) -> dict:
    return next(c for c in plan["checks"] if c["key"] == key)


# --- Acceptance 4: manual setup without URL, multiple/custom categories, languages -----


def test_manual_setup_without_url_multiple_categories_separate_languages(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    p = api.get(tok, f"/workspaces/{ws}/profile").json()
    r = api.put(tok, f"/workspaces/{ws}/profile", {
        "expected_version": p["version"], "legal_name": "Fjord Gulvservice ApS",
        "description": "Gulvafslibning i Storkøbenhavn", "website_url": None, "manual_setup": True,
        "city": "København", "postal_code": "2100", "timezone": "Europe/Copenhagen"})
    assert r.status_code == 200 and r.json()["manual_setup"] is True and r.json()["website_url"] is None
    # optimistic version control
    r = api.put(tok, f"/workspaces/{ws}/profile", {"expected_version": p["version"], "legal_name": "x", "description": "y"})
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"
    # suggested + custom categories
    assert api.post(tok, f"/workspaces/{ws}/categories", {"slug": "haandvaerk-gulvservice", "label": "ignored",
                                                          "is_primary": True}).status_code == 201
    r = api.post(tok, f"/workspaces/{ws}/categories", {"label": "Poolservice og vedligeholdelse"})
    assert r.status_code == 201 and r.json()["is_custom"] is True
    assert api.post(tok, f"/workspaces/{ws}/categories", {"label": "Poolservice og vedligeholdelse"}).status_code == 409
    cats = api.get(tok, f"/workspaces/{ws}/categories").json()
    assert len(cats) == 2 and cats[0]["is_primary"] and cats[0]["label"] == "Håndværk & Gulvservice"
    # four separate language levels
    ls = api.get(tok, f"/workspaces/{ws}/languages").json()
    r = api.put(tok, f"/workspaces/{ws}/languages", {"expected_version": ls["version"], "interface_language": "da",
                                                     "default_conversation_language": "da",
                                                     "enabled_conversation_languages": ["da", "en", "de"],
                                                     "report_language": "en"})
    assert r.status_code == 200
    j = r.json()
    assert j["report_language"] == "en" and j["enabled_conversation_languages"] == ["da", "en", "de"]
    r = api.put(tok, f"/workspaces/{ws}/languages", {"expected_version": j["version"], "interface_language": "da",
                                                     "default_conversation_language": "sv",
                                                     "enabled_conversation_languages": ["da"], "report_language": "da"})
    assert r.status_code == 422
    # goals: guidance + intent + capabilities; changing guidance keeps everything entered
    g = api.get(tok, f"/workspaces/{ws}/goals").json()
    r = api.put(tok, f"/workspaces/{ws}/goals", {"expected_version": g["version"], "product_intent": "reception",
                                                 "guidance_mode": "self_managed", "inbound_phone": True,
                                                 "callback": True, "booking": False, "conversation_goals": ["tilbud"]})
    assert r.status_code == 200 and r.json()["guidance_mode"] == "self_managed"
    assert api.get(tok, f"/workspaces/{ws}/profile").json()["description"] == "Gulvafslibning i Storkøbenhavn"
    assert len(api.get(tok, f"/workspaces/{ws}/categories").json()) == 2
    plan = api.plan(tok, ws)
    assert _task(plan, "business.profile")["status"] == "complete"
    assert _task(plan, "business.categories")["status"] == "complete"
    assert _task(plan, "languages.settings")["status"] == "complete"
    assert _task(plan, "goals.select")["status"] == "complete"
    assert plan["guidance_mode"] == "self_managed"


# --- Acceptance 5: resume after a new session ---------------------------------------


def test_resume_after_new_session(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    p = api.get(tok, f"/workspaces/{ws}/profile").json()
    api.put(tok, f"/workspaces/{ws}/profile", {"expected_version": p["version"], "legal_name": "Fjord",
                                               "description": "Gulve"})
    api.post(tok, f"/workspaces/{ws}/categories", {"label": "Gulve"})
    item = api.knowledge(tok, ws, "service", "Afslibning", {"unit": "m2"})
    plan_before = api.plan(tok, ws)
    assert plan_before["resume"]["open_drafts"] == 1
    next_before = plan_before["next_action"]["key"]
    # end session, start a new one
    assert api.post(tok, "/auth/logout").status_code == 204
    tok2 = api.login("owner-a@testmail.dk")
    ws_list = api.get(tok2, "/workspaces").json()
    assert ws_list[0]["id"] == ws
    plan_after = api.plan(tok2, ws)
    assert plan_after["next_action"]["key"] == next_before == "goals.select"
    assert plan_after["resume"]["open_drafts"] == 1
    assert plan_after["progress"] == plan_before["progress"]
    got = api.get(tok2, f"/workspaces/{ws}/knowledge/items/{item['id']}").json()
    assert got["open_draft"]["content"] == {"unit": "m2"}
    assert api.get(tok2, f"/workspaces/{ws}/profile").json()["description"] == "Gulve"


# --- Acceptance 6: assistant sees only approved knowledge; drafts never change the active version ----


def test_assistant_endpoint_only_approved_and_new_draft_keeps_active(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    item = api.knowledge(tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    v1 = item["open_draft"]["id"]
    assert api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"] == []  # draft hidden
    api.submit(tok, ws, v1)
    assert api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"] == []  # in_review hidden
    assert api.get(tok, f"/workspaces/{ws}/knowledge/review-queue").json()[0]["id"] == v1
    r = api.approve(tok, ws, v1)
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["version_no"] == 1
    active = api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()
    assert active["knowledge_revision"] == 1
    assert [i["content"] for i in active["items"]] == [{"price_net_minor": 14500}]
    # new draft: active version unchanged
    r = api.post(tok, f"/workspaces/{ws}/knowledge/items/{item['id']}/drafts",
                 {"title": "Afslibning", "content": {"price_net_minor": 15900}})
    assert r.status_code == 201 and r.json()["version_no"] == 2 and r.json()["status"] == "draft"
    v2 = r.json()["id"]
    assert api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"][0]["content"] == {"price_net_minor": 14500}
    # approved version cannot be edited in place
    r = api.put(tok, f"/workspaces/{ws}/knowledge/versions/{v1}", {"expected_edit_version": 1, "title": "x", "content": {}})
    assert r.status_code == 409 and r.json()["code"] == "version_not_editable"
    # a second open draft is refused
    assert api.post(tok, f"/workspaces/{ws}/knowledge/items/{item['id']}/drafts",
                    {"title": "y", "content": {}}).status_code == 409
    # approving the new draft creates version 2 and supersedes v1
    api.submit(tok, ws, v2)
    assert api.approve(tok, ws, v2).status_code == 200
    versions = api.get(tok, f"/workspaces/{ws}/knowledge/items/{item['id']}/versions").json()
    assert [(v["version_no"], v["status"]) for v in versions] == [(1, "superseded"), (2, "approved")]
    active = api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()
    assert active["knowledge_revision"] == 2 and active["items"][0]["content"] == {"price_net_minor": 15900}
    audit = [a["action"] for a in api.get(tok, f"/workspaces/{ws}/audit").json()["items"]]
    assert audit.count("knowledge.approved") == 2


def test_offer_rule_k04_at_least_40_m2_inclusive_dates(api, two_workspaces):
    content = {"discount_percent": 15, "condition": {"area_operator": "gte", "area_threshold_m2": 40},
               "starts_on": "2026-10-01", "ends_on_inclusive": "2026-11-30"}
    d = date(2026, 10, 28)
    assert offer_is_eligible(content, area_m2=39, on_date=d) is False
    assert offer_is_eligible(content, area_m2=40, on_date=d) is True
    assert offer_is_eligible(content, area_m2=41, on_date=d) is True
    assert offer_is_eligible(content, area_m2=65, on_date=date(2026, 11, 30)) is True
    assert offer_is_eligible(content, area_m2=65, on_date=date(2026, 12, 1)) is False
    assert offer_is_eligible(content, area_m2=65, on_date=date(2026, 9, 30)) is False
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    item = api.knowledge(tok, ws, "offer", "Efterårsrabat", content)
    # not approved yet: no eligibility from a draft
    r = api.get(tok, f"/workspaces/{ws}/knowledge/offers/{item['id']}/eligibility?area_m2=65&on_date=2026-10-28")
    assert r.status_code == 404
    api.submit(tok, ws, item["open_draft"]["id"])
    api.approve(tok, ws, item["open_draft"]["id"])
    r = api.get(tok, f"/workspaces/{ws}/knowledge/offers/{item['id']}/eligibility?area_m2=40&on_date=2026-10-28")
    assert r.json()["eligible"] is True
    r = api.get(tok, f"/workspaces/{ws}/knowledge/offers/{item['id']}/eligibility?area_m2=39&on_date=2026-10-28")
    assert r.json()["eligible"] is False
    bad = dict(content, starts_on="2026-12-01")
    assert api.post(tok, f"/workspaces/{ws}/knowledge/items", {"kind": "offer", "title": "Bad", "content": bad}).status_code == 422


# --- Acceptance 7: goal-dependent plan; unimplemented integrations block activation --------


def test_campaign_only_plan_has_no_phone_or_calendar_tasks(api, two_workspaces):
    t = two_workspaces
    plan_b = api.plan(t["tok_b"], t["ws_b"])
    keys = {x["key"] for x in plan_b["tasks"]}
    assert "reception.telephony_forwarding" not in keys and "booking.calendar" not in keys
    assert "reception.test_call" not in keys and "activation.reception" not in keys
    assert "campaign.first" in keys and "activation.campaigns" in keys
    assert _task(plan_b, "knowledge.opening_hours")["required"] is False
    camp = _task(plan_b, "activation.campaigns")
    assert camp["status"] == "not_available" and camp["blocked_by"][0]["type"] == "capability"
    assert {c["key"] for c in plan_b["checks"]} == {"profile.completeness", "languages.consistency",
                                                    "knowledge.approved_coverage", "knowledge.assistant_endpoint",
                                                    "campaign.test_call"}
    # reception workspace: phone tasks present; booking only after opting in
    plan_a = api.plan(t["tok_a"], t["ws_a"])
    keys_a = {x["key"] for x in plan_a["tasks"]}
    assert "reception.telephony_forwarding" in keys_a and "booking.calendar" not in keys_a
    g = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/goals").json()
    api.put(t["tok_a"], f"/workspaces/{t['ws_a']}/goals", {"expected_version": g["version"], "product_intent": "reception",
                                                           "inbound_phone": True, "booking": True})
    plan_a = api.plan(t["tok_a"], t["ws_a"])
    cal = _task(plan_a, "booking.calendar")
    assert cal["required"] and cal["status"] == "not_available" and cal["capability_status"] == "not_implemented"
    act = _task(plan_a, "activation.reception")
    assert act["status"] == "not_available"
    assert {b["type"] for b in act["blocked_by"]} == {"capability", "dependency"}
    assert _check(plan_a, "calendar.connection")["runnable"] is False
    # running an unimplemented check records nothing
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/setup/checks/calendar.connection/run")
    assert r.status_code == 501 and r.json()["code"] == "not_implemented"
    assert _check(api.plan(t["tok_a"], t["ws_a"]), "calendar.connection")["status"] == "untested"
    # activation commands remain separate and fail honestly
    assert api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/setup/activate/reception").status_code == 501
    assert api.post(t["tok_b"], f"/workspaces/{t['ws_b']}/setup/activate/campaigns").status_code == 501


def test_required_task_cannot_be_skipped_optional_can(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    r = api.post(tok, f"/workspaces/{ws}/setup/tasks/knowledge.services/skip")
    assert r.status_code == 409 and r.json()["code"] == "task_required"
    r = api.post(tok, f"/workspaces/{ws}/setup/tasks/knowledge.coverage_area/skip")
    assert r.status_code == 200 and r.json()["status"] == "skipped"
    plan = api.plan(tok, ws)
    assert _task(plan, "knowledge.coverage_area")["status"] == "skipped"
    assert plan["progress"]["required_complete"] == 0  # skips never count as complete
    r = api.post(tok, f"/workspaces/{ws}/setup/tasks/knowledge.coverage_area/unskip")
    assert r.json()["status"] == "not_started"


def test_next_action_and_permission_block_for_staff(api, two_workspaces):
    t = two_workspaces
    owner, ws = t["tok_a"], t["ws_a"]
    staff = api.add_member(owner, ws, "staff2@testmail.dk", "staff")
    item = api.knowledge(staff, ws, "service", "Lakering")
    api.submit(staff, ws, item["open_draft"]["id"])
    plan_staff = api.plan(staff, ws)
    review = _task(plan_staff, "knowledge.review")
    assert review["required"] and review["status"] == "blocked" and review["blocked_by"][0]["type"] == "permission"
    assert review["you_can_act"] is False
    plan_owner = api.plan(owner, ws)
    assert _task(plan_owner, "knowledge.review")["status"] == "in_progress"
    # G07: owner assigns the review task to themself; staff cannot assign to others
    members = api.get(owner, f"/workspaces/{ws}/members").json()
    owner_uid = next(m["user_id"] for m in members if m["role"] == "owner")
    r = api.put(owner, f"/workspaces/{ws}/setup/tasks/knowledge.review/assignee", {"user_id": owner_uid})
    assert r.status_code == 200 and r.json()["assigned_to"] == owner_uid
    assert api.put(staff, f"/workspaces/{ws}/setup/tasks/knowledge.review/assignee", {"user_id": owner_uid}).status_code == 403


# --- Acceptance 8: config change invalidates only dependent checks -------------------------


def test_config_change_stales_dependent_checks_only(api, two_workspaces):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    p = api.get(tok, f"/workspaces/{ws}/profile").json()
    api.put(tok, f"/workspaces/{ws}/profile", {"expected_version": p["version"], "legal_name": "Fjord", "description": "d"})
    api.post(tok, f"/workspaces/{ws}/categories", {"label": "Gulve"})
    for kind, title, content in (("service", "Afslibning", {}),
                                 ("opening_hours", "Tider", {"weekly": [{"days": ["mon"], "open": "08:00", "close": "16:00"}]})):
        it = api.knowledge(tok, ws, kind, title, content)
        api.submit(tok, ws, it["open_draft"]["id"])
        api.approve(tok, ws, it["open_draft"]["id"])
    r = api.post(tok, f"/workspaces/{ws}/setup/checks/run-all")
    assert r.status_code == 200
    assert {x["check_key"]: x["status"] for x in r.json()["results"]} == {
        "profile.completeness": "passed", "languages.consistency": "passed",
        "knowledge.approved_coverage": "passed", "knowledge.assistant_endpoint": "passed"}
    assert {s["check_key"] for s in r.json()["skipped"]} >= {"telephony.test_call", "telephony.forwarding"}
    plan = api.plan(tok, ws)
    assert _task(plan, "checks.server")["status"] == "complete"
    prof = _check(plan, "profile.completeness")
    assert prof["config_versions"]["profile"] == 2 and prof["environment"] == "server:test" and prof["evidence"]
    # change languages → only languages.consistency stale
    ls = api.get(tok, f"/workspaces/{ws}/languages").json()
    api.put(tok, f"/workspaces/{ws}/languages", {"expected_version": ls["version"], "interface_language": "da",
                                                 "default_conversation_language": "en",
                                                 "enabled_conversation_languages": ["da", "en"], "report_language": "da"})
    plan = api.plan(tok, ws)
    assert _check(plan, "languages.consistency")["status"] == "stale"
    assert _check(plan, "languages.consistency")["stale_reason"]
    for k in ("profile.completeness", "knowledge.approved_coverage", "knowledge.assistant_endpoint"):
        assert _check(plan, k)["status"] == "passed", k
    assert _task(plan, "checks.server")["status"] == "in_progress"
    assert _task(plan, "checks.server")["stale_checks"] == ["languages.consistency"]
    # approving new knowledge → only knowledge checks stale; profile stays passed
    it = api.knowledge(tok, ws, "fact", "Parkering", {"text": "Gratis parkering i gården"})
    api.submit(tok, ws, it["open_draft"]["id"])
    api.approve(tok, ws, it["open_draft"]["id"])
    plan = api.plan(tok, ws)
    assert _check(plan, "knowledge.approved_coverage")["status"] == "stale"
    assert _check(plan, "knowledge.assistant_endpoint")["status"] == "stale"
    assert _check(plan, "profile.completeness")["status"] == "passed"
    # re-run restores; history keeps the stale record
    api.post(tok, f"/workspaces/{ws}/setup/checks/run-all")
    assert _task(api.plan(tok, ws), "checks.server")["status"] == "complete"
    hist = api.get(tok, f"/workspaces/{ws}/setup/checks/history").json()["items"]
    assert any(h["status"] == "stale" for h in hist)
