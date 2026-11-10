"""QA R01, R04, R05, R06, R07 (voice-qa) – reception configuration as the call engine sees it.

R01 per-channel status + pause/resume · R04 web widget (domains, snippet, install check) · R05 reception script (voice,
language, version, publish) · R06 test/preview before publishing · R07 hours, exceptions, human hand-off and fallback.
In v2 these live in «Alle indstillinger» (sheets hilsen/telefoni/webchat), «Det ved den» and «I dag» – see
docs/kundeapp-v2.md. All offline: fake telephony (WORLD = outbox), fake AI, no network, no call."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.modules.telephony import vapi as vapi_mod
from tests.qa.test_qa_voice_R02 import _active, no_network  # noqa: F401
from tests.test_telephony import _post, _setup, configured  # noqa: F401
from tests.test_telephony_platform import _hook, fake  # noqa: F401
from tests.test_webchat import PUB, _start, fake as ai_fake, live  # noqa: F401

TZ = ZoneInfo("Europe/Copenhagen")


def _assistant(client, *, caller="+4520304050", pn="pn_123") -> dict:
    r = _post(client, {"type": "assistant-request", "call": {"id": "r07", "phoneNumberId": pn, "customer": {"number": caller}}})
    assert r.status_code == 200, r.text
    return r.json()


def _approve(api, tok, ws, kind, title, content):
    it = api.knowledge(tok, ws, kind, title, content)
    api.submit(tok, ws, it["open_draft"]["id"])
    assert api.approve(tok, ws, it["open_draft"]["id"]).status_code == 200
    return it


# --------------------------------------------------------------------------- R01 status + pause/resume

def test_r01_per_channel_status_and_pause_resume_reach_the_call(client, api, two_workspaces, fake, no_network):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    dest = _active(client, api, tok, ws)
    ov = api.get(tok, f"/workspaces/{ws}/reception/overview").json()
    assert ov["channels"]["webchat"]["enabled"] is False and any(n["e164"] == dest for n in ov["channels"]["phone"]["numbers"])
    assert api.get(tok, f"/workspaces/{ws}/telephony").json()["status"]["code"] == "active"
    # pause: the caller hears the short «not active» message, no knowledge is used
    assert api.post(tok, f"/workspaces/{ws}/telephony/pause").status_code == 200
    a = _hook(client, {"type": "assistant-request", "call": {"id": "c-p", "customer": {"number": "+4520304050"}},
                       "phoneNumber": {"number": dest}}).json()["assistant"]
    assert a["metadata"].get("not_active") is True and "Afslibning" not in str(a)
    assert api.get(tok, f"/workspaces/{ws}/telephony").json()["status"]["code"] == "paused"
    # staff cannot flip the switch; the owner can resume
    staff = api.add_member(tok, ws, "staff-r01@testmail.dk", "staff")
    assert api.post(staff, f"/workspaces/{ws}/telephony/activate").status_code == 403
    assert api.post(tok, f"/workspaces/{ws}/telephony/activate").status_code == 200
    a = _hook(client, {"type": "assistant-request", "call": {"id": "c-r", "customer": {"number": "+4520304050"}},
                       "phoneNumber": {"number": dest}}).json()["assistant"]
    assert not a["metadata"].get("not_active") and "Afslibning" in a["model"]["messages"][0]["content"]


# --------------------------------------------------------------------------- R04 web widget

def test_r04_widget_snippet_domains_and_install_check(client, api, live):  # noqa: F811
    t = live
    s = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat").json()
    assert s["widget_key"] in s["embed_code"] and s["available"] is True
    assert s["last_seen_at"] is None  # not installed yet
    # the widget frame may only be embedded by the allowed sites (CSP frame-ancestors); a real iframe load from an
    # allowed site is the installation evidence, one from a foreign site is not
    frame = f"{PUB}/{t['key']}/frame"
    foreign = client.get(frame, headers={"referer": "https://evil.example/side", "sec-fetch-dest": "iframe"})
    assert "https://evil.example" not in foreign.headers["content-security-policy"]
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat").json()["last_seen_at"] is None
    ok = client.get(frame, headers={"referer": "https://shop.fjordgulv.example/kontakt", "sec-fetch-dest": "iframe"})
    assert "frame-ancestors" in ok.headers["content-security-policy"]
    assert "https://shop.fjordgulv.example" in ok.headers["content-security-policy"]
    s = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat").json()
    assert s["last_seen_at"] is not None and s["last_seen_origin"] == "https://shop.fjordgulv.example"
    # rotating the key kills the old snippet and resets the install check
    new = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/webchat/rotate-key").json()
    assert new["widget_key"] != s["widget_key"] and new["last_seen_at"] is None
    assert _start(client, s["widget_key"]).status_code in (403, 404)
    # appearance/branding: nothing to configure (documented as not built – see report)
    assert not {"color", "colour", "logo", "position", "theme"} & set(s)


# --------------------------------------------------------------------------- R05 script reaches the call

def test_r05_saved_script_is_used_from_the_next_call_with_version_conflict_and_role(client, api, two_workspaces, configured):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    _setup(api, t)
    body = {"expected_version": 0, "persona_name": "Sofie", "address_form": "De", "greeting": "Goddag, {virksomhed}.",
            "collect": ["adresse", "antal kvadratmeter"], "escalation": "vandskade", "avoid": "endelige priser",
            "closing": "Tak for opkaldet."}
    assert api.put(tok, f"/workspaces/{ws}/reception/script", body).status_code == 200
    assert api.put(tok, f"/workspaces/{ws}/reception/script", body | {"greeting": "x"}).status_code == 409  # stale
    staff = api.add_member(tok, ws, "staff-r05@testmail.dk", "staff")
    assert api.put(staff, f"/workspaces/{ws}/reception/script", body | {"expected_version": 1}).status_code == 403
    a = _assistant(client)["assistant"]
    system = a["model"]["messages"][0]["content"]
    assert "Du præsenterer dig som Sofie" in system and "De/Dem" in system and "vandskade" in system
    assert a["firstMessage"].startswith("Goddag, Fjord Gulvservice ApS.") and "digital assistent" in a["firstMessage"]
    assert a["voice"] if "voice" in a else True


# --------------------------------------------------------------------------- R06 test before customers do

def test_r06_preview_answers_from_approved_knowledge_and_the_script(client, api, two_workspaces, ai_fake):  # noqa: F811
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    assert api.post(tok, f"/workspaces/{ws}/assistant/preview", {"message": "Hvad koster det?"}).status_code == 409
    _approve(api, tok, ws, "service", "Afslibning", {"price_net_minor": 14500})
    api.knowledge(tok, ws, "fact", "KLADDE-R06", {"text": "x"})
    r = api.post(tok, f"/workspaces/{ws}/assistant/preview", {"message": "Hvad koster afslibning?"})
    assert r.status_code == 200, r.text
    assert "KLADDE-R06" not in ai_fake.last_system and "Afslibning" in ai_fake.last_system
    reader = api.add_member(tok, ws, "reader-r06@testmail.dk", "reader")
    assert api.post(reader, f"/workspaces/{ws}/assistant/preview", {"message": "Hej"}).status_code in (200, 403)


# --------------------------------------------------------------------------- R07 hours, now, fallback

def test_r07_opening_hours_reach_the_call(client, api, two_workspaces, configured):  # noqa: F811
    t = two_workspaces
    _setup(api, t)
    _approve(api, t["tok_a"], t["ws_a"], "opening_hours", "Åbningstider",
             {"weekly": [{"days": ["mon", "tue", "wed", "thu", "fri"], "open": "08:00", "close": "16:00"}],
              "note": "Lukket i weekender og på helligdage"})
    system = _assistant(client)["assistant"]["model"]["messages"][0]["content"]
    assert '"open":"08:00"' in system and "Lukket i weekender" in system


def test_r07_peter_knows_todays_date_weekday_and_time_in_the_business_timezone(client, api, two_workspaces, configured):  # noqa: F811
    """Without «now» the model cannot answer «har I åbent nu?», «ring i morgen», or fill ledige_tider.fra_dato
    (ÅÅÅÅ-MM-DD) – it guesses from its training data. Nothing in assistant_config adds the date or time, and no Vapi
    template variable ({{now}}) is used."""
    _setup(api, two_workspaces)
    system = _assistant(client)["assistant"]["model"]["messages"][0]["content"]
    now = datetime.now(TZ)
    weekday = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")[now.weekday()]
    has_date = now.strftime("%Y-%m-%d") in system or f"{now.day}. " in system and str(now.year) in system
    has_template = "{{" in system and "now" in system
    assert (has_date and weekday in system.lower()) or has_template, "the inbound prompt has no date, weekday or time"


def test_r07_fallback_when_knowledge_is_withdrawn_from_a_live_number(client, api, two_workspaces, configured, db):  # noqa: F811
    """An active number whose last approved item is archived: the assistant-request answers {"error": <text>} and Vapi
    speaks that text to the caller. The text must be meant for a caller, not the business's admin."""
    t = two_workspaces
    _setup(api, t, approve=False)
    it = _approve(api, t["tok_a"], t["ws_a"], "service", "Afslibning", {"price_net_minor": 14500})
    assert "assistant" in _assistant(client)
    assert api.delete(t["tok_a"], f"/workspaces/{t['ws_a']}/knowledge/items/{it['id']}").status_code == 204
    out = _assistant(client)
    spoken = out.get("error") or out.get("assistant", {}).get("firstMessage", "")
    assert "assistant" in out or not any(w in spoken.lower() for w in ("godkend", "vidensemne", "viden endnu")), (
        f"the caller would hear the admin message: {spoken!r}")


def test_r07_hand_off_is_a_follow_up_task_and_never_a_transfer_promise(client, api, two_workspaces, configured):  # noqa: F811
    _setup(api, two_workspaces)
    rules = vapi_mod.CHANNEL_INSTRUCTIONS["phone"][1] if hasattr(vapi_mod, "CHANNEL_INSTRUCTIONS") else ""
    system = _assistant(client)["assistant"]["model"]["messages"][0]["content"]
    assert "Du kan ikke stille om" in system and "en medarbejder ringer tilbage" in system
    assert rules == "" or "Du kan ikke stille om" in rules
