"""Every Dialogbot Privat mail, in every language (QA F-JP-03, F-JP-06, F-JP-07, F-JP-08, F-JP-15, F-JE-04, F-JE-06).

Renders ALL builders in app/modules/integrations/privat_mails.py (found by inspection, so a new one cannot be skipped)
and demands: audience «privat» (orange, Privat icon, «Dialogbot Privat»), one button to a Privat route, the recipient's
language for all 8 languages, and one register (formal de/es/fr/it). Code under app/modules/privat never builds a mail
by hand – it must go through these builders."""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.core.languages import LANGUAGES
from app.modules.integrations import email_templates as tpl
from app.modules.integrations import email_texts as tx
from app.modules.integrations import privat_mails as pm

ROOT = Path(__file__).resolve().parents[1]
ERHVERV_WORDS = ("AI-receptionist", "arbejdsrum", "virksomhed", "receptionist", "Rezeption", "réceptionniste")
# the account mails and the billing mails Privat shares with Erhverv (privat_mails.billing, F-PBQ-08)
SHARED_PREFIXES = ("verify_", "billing_", "receipt_", "failed_", "refund_", "trial_")
INFORMAL = {"de": r"\b(du|dein\w*|dich|dir)\b", "es": r"\b(tu|tus|te|podrás|Confirma)\b",
            "fr": r"\b(tu|ton|ta|tes|Confirme)\b", "it": r"\b(tuo|tua|tuoi|Conferma|puoi)\b"}


def _builders() -> set[str]:
    return {n for n, f in inspect.getmembers(pm, inspect.isfunction)
            if f.__module__ == pm.__name__ and not n.startswith("_") and f.__annotations__.get("return") == "Email"}


def _privat_route(url: str) -> bool:
    parts = urlsplit(url)
    if parts.path.startswith("/privat/"):
        return True
    q = parse_qs(parts.query)
    return parts.path in ("/verify-email", "/password/reset") and q.get("for") == ["privat"]


def test_every_privat_builder_is_in_the_samples():
    names = _builders()
    assert names and names <= set(pm.samples()), f"add to privat_mails.samples(): {names - set(pm.samples())}"


def test_every_privat_mail_is_privat_has_a_privat_button_and_is_in_every_language():
    da = pm.samples("da")
    for lang in LANGUAGES:
        for key, mail in pm.samples(lang).items():
            where = f"{key}/{lang}"
            h, text = mail.html(), mail.text()
            assert mail.audience == "privat", where
            assert tpl.PRIVAT_ACCENT in h and tpl.ACCENT not in h, f"{where}: not the Privat orange"
            assert "/icons/privat-icon-192.png" in h and "Dialogbot Privat" in h, where
            assert mail.button_url and _privat_route(mail.button_url), f"{where}: {mail.button_url}"
            assert len(re.findall(r'class="btna"', h)) == 1, where
            assert mail.lang == lang and f'<html lang="{lang}">' in h, where
            assert tx.t(lang, "regards") in text and tx.t(lang, "company_line") in text, where
            for w in ERHVERV_WORDS:
                assert w not in text, f"{where}: Erhverv word {w!r}"
            if lang != "da":  # the fixed frame really is translated (a button may be the same word in Norwegian)
                assert mail.footer_reason != da[key].footer_reason, f"{where}: Danish footer"
            back = tpl.from_payload({"to_email": "a@b.dk", "email": tpl.to_payload(mail)})
            assert back.html() == h and back.audience == "privat", where


def test_privat_texts_keep_one_register():
    """F-JP-15: de/es/fr/it mails are formal (Sie/usted/vous/Lei) in the layout, so the Privat texts are too."""
    from app.modules.integrations.email_texts_privat import PRIVAT_TEXTS

    for lang, rx in INFORMAL.items():
        keys = {k: v for k, v in tx.TEXTS[lang].items() if (k in PRIVAT_TEXTS[lang] or k.startswith(SHARED_PREFIXES))
                and not k.endswith(("_button", "_open_task"))}  # a button label is a label, not an address
        bad = {k: v for k, v in keys.items() if re.search(rx, v)}
        assert not bad, f"{lang}: {bad}"


def test_privat_code_never_builds_a_mail_by_hand():
    offenders = []
    for p in sorted((ROOT / "app" / "modules" / "privat").rglob("*.py")):
        s = p.read_text(encoding="utf-8")
        offenders += [f"{p.name}:{s[:m.start()].count(chr(10)) + 1}" for m in re.finditer(r"tpl\.Email\(", s)]
    assert offenders == [], f"use app.modules.integrations.privat_mails: {offenders}"


def test_sms_code_in_every_language():
    texts = {lang: pm.sms_code("123456", lang) for lang in LANGUAGES}
    assert texts["da"] == "Din kode til Dialogbot er 123456. Den gælder i 10 minutter."
    assert len(set(texts.values())) == len(LANGUAGES) and all("123456" in v for v in texts.values())
