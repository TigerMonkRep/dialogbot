"""QA X05 (voice-qa): "Prøv-den: chat → besøgende beder om opkald → Peter (ikke Clara) ringer; verificeret nummer;
uden live-opkald i test (outbox/simulering)."

The /proev page (web/src/app/proev/proev-chat.tsx) talks to POST /api/v1/demo-call/chat (Peter answers from the
sales workspace's approved knowledge) and then POST /api/v1/demo-call, which builds Peter's outbound assistant and
hands it to campaigns.create_call (Vapi POST /call). Here create_call is the `sales` fixture's in-memory outbox, so
no call is ever placed. Also covers: no "privat preview"/"invitationskode" wording in Peter's prompts or seed
knowledge; nothing forbids Peter from mentioning Dialogbot Privat."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.models import DemoCall
from app.modules.ai import service as ai
from app.modules.sales import script
from app.modules.sales import service as sales_service
from app.modules.voices.standard import STANDARD_VOICES
from tests.test_sales_demo_calls import sales  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[2]
OTHER_NAMES = ("Clara", "Astrid")
PREVIEW_WORDING = re.compile(r"privat preview|private preview|invitationskode|invitation code|forhåndskode|preview-kode",
                             re.IGNORECASE)
LOCALES = ("da", "en", "de", "es", "fr", "it", "no", "sv")


def _runner():
    spec = importlib.util.spec_from_file_location("qa_voice_run_cases", ROOT / "qa/voice/run_cases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _case(cid: str) -> dict:
    return next(c for c in _runner().load(ROOT / "qa/voice/cases/X05.yaml") if c["id"] == cid)


def _capture_system(monkeypatch) -> list[str]:
    seen: list[str] = []
    real = ai.log_call

    def spy(db, workspace, provider, *, system, **kw):
        seen.append(system)
        return real(db, workspace, provider, system=system, **kw)

    monkeypatch.setattr(ai, "log_call", spy)
    return seen


def _proev_body(phone="20 30 40 50", company="Hansen VVS", industry="haandvaerk", **extra):
    """Exactly what proev-chat.tsx posts (no name field: the chat never asks for one)."""
    info_version = sales_service.CONSENT_VERSION_WEB
    return {"phone": phone, "company": company, "consent": True, "consent_version": info_version, "website": "",
            "industry": industry, "industry_other": None, **extra}


# --------------------------------------------------------------------------- the chat is Peter

def test_x05_chat_is_peter_and_cannot_place_calls_itself(client, sales, monkeypatch):  # noqa: F811
    seen = _capture_system(monkeypatch)
    r = client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": "Hvem er du? Ring til mig."}]})
    assert r.status_code == 200, r.text
    system = seen[-1]
    assert "Du hedder Peter og er Dialogbots digitale receptionist" in system
    assert "Du kan ikke selv ringe" in system and "«Ja, ring til mig»" in system  # the button places the call
    for old in OTHER_NAMES:
        assert old not in system
    assert not PREVIEW_WORDING.search(system)
    assert sales["calls"] == []  # chatting never rings anybody
    info = client.get("/api/v1/demo-call").json()
    assert info["agent"] == "Peter" and [v["key"] for v in info["voices"]] == ["peter"]
    assert "Peter fra Dialogbot" in info["consent_text"]


def test_x05_proev_chat_greets_as_peter_in_every_locale():
    for lang in LOCALES:
        site = json.loads((ROOT / f"web/src/i18n/messages/{lang}/site.json").read_text(encoding="utf-8"))
        chat = json.dumps(site["proev"], ensure_ascii=False)
        assert "Peter" in site["proev"]["chat"]["greeting"], lang
        for old in OTHER_NAMES:
            assert old not in chat, (lang, old)


# --------------------------------------------------------------------------- chat → "ring mig op" → Peter rings

def test_x05_chat_then_call_request_rings_with_peter_on_the_entered_number(client, sales, db):  # noqa: F811
    assert client.post("/api/v1/demo-call/chat", json={"messages": [{"role": "user", "content": "Kan I tage telefonen for en VVS'er?"}]}).status_code == 200
    r = client.post("/api/v1/demo-call", json=_proev_body(voice="camilla"))  # an old client asking for Camilla
    assert r.status_code == 202 and r.json() == {"status": "calling"}
    assert len(sales["calls"]) == 1  # placed into the outbox stub – never to Vapi
    payload = sales["calls"][0]
    a = payload["assistant"]
    assert payload["customer"]["number"] == "+4520304050"
    assert a["firstMessage"].startswith("Hej, det er Peter fra Dialogbot. Jeg er en digital assistent")
    assert "Hansen VVS" in a["firstMessage"]
    assert a["voice"]["voiceId"] == STANDARD_VOICES["peter"]["voice"]["voiceId"]
    system = a["model"]["messages"][0]["content"]
    assert f"Du hedder {script.AGENT_NAME}" in system and "Peter fra Dialogbot" in system
    for old in OTHER_NAMES:
        assert old not in system and old not in a["firstMessage"]
    assert not PREVIEW_WORDING.search(system)
    # the number the visitor typed is known: Peter confirms it, never asks for it
    assert "det nummer, du skrev på hjemmesiden, er tyve, tredive, fyrre, halvtreds" in system
    assert a["artifactPlan"] == {"recordingEnabled": False} and a["maxDurationSeconds"] <= 420
    d = db.query(DemoCall).one()
    assert d.voice_key == "peter" and d.consent_version == sales_service.CONSENT_VERSION_WEB
    assert "Peter fra Dialogbot" in d.consent_text
    ok, why = _runner().score(_case("X05-02"), [{"role": "assistant", "text": a["firstMessage"]}])
    assert ok, why
    (ROOT / "qa/evidence/X05/demo_call_payload.json").write_text(json.dumps(
        {"customer": payload["customer"], "firstMessage": a["firstMessage"],
         "voice": {k: a["voice"][k] for k in ("provider", "voiceId", "model", "language")},
         "maxDurationSeconds": a["maxDurationSeconds"], "artifactPlan": a["artifactPlan"]},
        ensure_ascii=False, indent=1))


@pytest.mark.xfail(strict=True, reason="F-VQ-05-X05: needs-decision – number verification before Peter rings is not built")
def test_x05_the_number_is_verified_before_peter_rings(client, sales, db):  # noqa: F811
    """X05: "verificeret nummer". Today the public door rings whatever Danish number is typed, as soon as the box is
    ticked: the person who ticks "Ja tak, Peter ... må ringe mig op på dette nummer" is never shown to own it. Expected:
    a proof of the number (code by SMS or a missed-call check, as /telephony/verify does for the business number)
    before Peter's call is placed."""
    r = client.post("/api/v1/demo-call", json=_proev_body(phone="21 30 40 50", company="Naboens Firma"))
    placed = len(sales["calls"])
    assert placed == 0 or r.json().get("status") != "calling", (
        f"Peter rang +4521304050 immediately ({placed} call placed) without any proof that the visitor owns the number")


# --------------------------------------------------------------------------- Peter's prompts and seed knowledge

def test_x05_no_preview_wording_in_peters_prompts_and_seed_knowledge_and_privat_is_not_forbidden():
    spec = importlib.util.spec_from_file_location("seed_sales", ROOT / "scripts/seed_sales_knowledge.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    from app.modules.telephony import phone_languages as pl

    sources = {
        "CHANNEL_INSTRUCTIONS": json.dumps(ai.CHANNEL_INSTRUCTIONS, ensure_ascii=False),
        "CHAT_INSTRUCTIONS": sales_service.CHAT_INSTRUCTIONS,
        "FEATURES": script.FEATURES,
        "manuscript": script.manuscript(name="Mette", company="Hansen VVS", industry=None),
        "first_message": script.first_message("Mette", "Hansen VVS", None),
        "peter-sales-v1.txt": (ROOT / "app/modules/sales/data/peter-sales-v1.txt").read_text(encoding="utf-8"),
        "seed_sales_knowledge.ITEMS": json.dumps(seed.ITEMS, ensure_ascii=False),
        "phone greetings": json.dumps(pl.GREETING, ensure_ascii=False),
        "consent texts": sales_service.CONSENT_TEXT_WEB + sales_service.CONSENT_TEXT_SELLER,
    }
    for name, text in sources.items():
        assert not PREVIEW_WORDING.search(text), f"{name}: {PREVIEW_WORDING.search(text).group(0)!r}"
        # Peter may mention Dialogbot Privat: no rule tells him not to
        assert not re.search(r"(nævn|tal|sig)\w*\s+(aldrig|ikke)[^.\n]{0,40}privat\b", text, re.IGNORECASE), name
