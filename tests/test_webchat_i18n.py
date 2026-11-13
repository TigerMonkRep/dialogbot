"""The chat widget in the platform's 8 languages (Fürster 13/11), including W04's code step; and M03: the app tells
the customer their workspace is paused (only their own workspace), while the chat and its code SMS go on."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import pytest
from sqlalchemy import text

from app.modules.webchat import texts
from app.worker import runner
from tests.test_leads import chat, fake  # noqa: F401 – fixtures
from tests.webchat_phone import request_code

STATIC = Path(texts.__file__).parent / "static"
PUB = "/api/v1/public/webchat"


def test_every_language_has_the_same_keys_and_placeholders():
    da = texts.TEXTS["da"]
    assert set(texts.TEXTS) == set(texts.LANGUAGES)
    for lang, tx in texts.TEXTS.items():
        assert set(tx) == set(da), (lang, set(da) ^ set(tx))
        for k, v in tx.items():
            assert set(re.findall(r"{\w+}", v)) == set(re.findall(r"{\w+}", da[k])), (lang, k)
            assert v.strip(), (lang, k)
        assert len(tx["weekdays"].split("|")) == 7


def test_frame_js_has_no_danish_text_of_its_own_and_every_key_exists():
    js = (STATIC / "frame.js").read_text(encoding="utf-8")
    assert not re.search(r"[æøåÆØÅ]", js)
    used = set(re.findall(r'\b[TE]\("(\w+)"', js)) | set(re.findall(r'"(\w+)"\s*[,}]', js.split("var byCode =")[1].split("};")[0]))
    used -= {"too_soon", "sms_rate_limited", "phone_invalid", "code_expired", "too_many_attempts", "slot_taken",
             "rate_limited", "conversation_limit", "daily_limit", "webchat_unavailable"}
    assert used and used <= set(texts.TEXTS["da"]), used - set(texts.TEXTS["da"])
    loader = (STATIC / "loader.js").read_text(encoding="utf-8")
    for lang in texts.LANGUAGES:
        assert f"\n    {lang}: [" in loader


@pytest.mark.parametrize(("query", "accept", "want"), [
    ("", None, "da"), ("?lang=de", None, "de"), ("?lang=nb", "en", "no"), ("", "sv-SE,sv;q=0.9,en;q=0.5", "sv"),
    ("", "pl,fr;q=0.8", "fr"), ("?lang=pl", "pl", "da"),
])
def test_the_frame_follows_the_requested_or_the_visitors_language(client, chat, query, accept, want):  # noqa: F811
    h = {"accept-language": accept} if accept else {}
    r = client.get(f"{PUB}/{chat['key']}/frame{query}", headers=h)
    assert r.status_code == 200
    assert f'<html lang="{want}">' in r.text
    cfg = json.loads(unescape(re.search(r'data-config="([^"]*)"', r.text).group(1)))
    assert cfg["lang"] == want and cfg["t"] == texts.TEXTS[want]
    assert cfg["unavailable"] == texts.TEXTS[want]["unavailable"]
    if want == "da":
        assert cfg["greeting"].startswith("Hej! Jeg er ")  # unchanged Danish default
    else:
        assert cfg["greeting"] == texts.TEXTS[want]["greeting"].format(name="Fjord Gulvservice ApS")


def test_the_business_language_when_the_visitor_gives_none(client, chat, db):  # noqa: F811
    db.execute(text("update language_settings set default_conversation_language = 'it' where workspace_id = :w"),
               {"w": chat["ws_a"]})
    db.commit()
    from app.models import LanguageSettings

    if db.get(LanguageSettings, chat["ws_a"]) is None:
        pytest.skip("workspace has no language settings row")
    r = client.get(f"{PUB}/{chat['key']}/frame")
    assert '<html lang="it">' in r.text


def test_callback_windows_in_the_widgets_language_keep_their_keys(client, chat):  # noqa: F811
    da = client.get(f"{PUB}/{chat['key']}/callback-windows").json()["options"]
    en = client.get(f"{PUB}/{chat['key']}/callback-windows?lang=en").json()["options"]
    assert [o["key"] for o in da] == [o["key"] for o in en]
    assert da[0]["label"] == "Hurtigst muligt" and en[0]["label"] == "As soon as possible"
    for o in en[1:]:
        assert ("morning (8–12)" in o["label"]) or ("afternoon (12–16)" in o["label"])


def test_a_custom_greeting_is_shown_as_written(client, chat, api):  # noqa: F811
    s = api.get(chat["tok_a"], f"/workspaces/{chat['ws_a']}/webchat").json()
    api.put(chat["tok_a"], f"/workspaces/{chat['ws_a']}/webchat", {"expected_version": s["version"], "enabled": True,
            "allowed_origins": s["allowed_origins"], "greeting": "Velkommen hos Fjord!"})
    r = client.get(f"{PUB}/{chat['key']}/frame?lang=en")
    cfg = json.loads(unescape(re.search(r'data-config="([^"]*)"', r.text).group(1)))
    assert cfg["greeting"] == "Velkommen hos Fjord!"


# --------------------------------------------------------------------------- M03 banner

def test_the_paused_flag_is_on_the_own_workspace_only(api, two_workspaces, db):
    t = two_workspaces
    db.execute(text("update workspaces set ops_suspended_at = :n, ops_suspended_reason = 'Twilio-hændelse INTERN' "
                    "where id = :w"), {"n": datetime.now(UTC), "w": t["ws_a"]})
    db.commit()
    a = api.get(t["tok_a"], "/workspaces").json()
    assert [(w["id"], w["suspended"]) for w in a] == [(t["ws_a"], True)]
    assert "INTERN" not in json.dumps(a)  # the operator's reason stays internal
    assert api.get(t["tok_a"], f"/workspaces/{t['ws_a']}").json()["suspended"] is True
    b = api.get(t["tok_b"], "/workspaces").json()
    assert [(w["id"], w["suspended"]) for w in b] == [(t["ws_b"], False)]
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_a']}").status_code == 404


def test_a_paused_workspace_still_sends_its_chat_codes(client, chat, db):  # noqa: F811
    from app.modules.integrations.connectors.fakes import WORLD

    WORLD.reset()
    db.execute(text("update workspaces set ops_suspended_at = now() where id = :w"), {"w": chat["ws_a"]})
    db.commit()
    r = request_code(client, chat["key"], chat["conv"], "20 30 40 50", send=False)
    assert r.status_code == 202, r.text
    runner.drain()
    assert [m["to"] for m in WORLD.sms] == ["+4520304050"]
    WORLD.reset()
