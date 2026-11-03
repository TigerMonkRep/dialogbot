"""Multi-language e-mails and caller SMS: every language has every text, Danish is unchanged, and each mail is
queued in the recipient's language (account mails: the user's interface language; invitations: the workspace's;
notifications: each recipient's). SMS to callers follow the workspace's default conversation language."""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.languages import LANGUAGES
from app.models import EmailDelivery, LanguageSettings, OutboxEvent, User, Workspace
from app.modules.integrations import email_templates as tpl
from app.modules.integrations import email_texts as tx
from app.modules.integrations import sms_templates as sms_t

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


# --- the dictionaries ------------------------------------------------------------------------------------------------

def test_every_language_has_every_email_key_with_the_same_placeholders():
    assert set(tx.TEXTS) == set(LANGUAGES) == set(tx.NUMBER_SEPARATORS) == set(tx.GREETING_WORDS)
    da = tx.TEXTS["da"]
    for lang, table in tx.TEXTS.items():
        assert set(table) == set(da), f"{lang}: missing {set(da) - set(table)}, extra {set(table) - set(da)}"
        for key, text in table.items():
            assert text.strip(), f"{lang}.{key} is empty"
            assert set(_PLACEHOLDER.findall(text)) == set(_PLACEHOLDER.findall(da[key])), f"{lang}.{key}"


def test_every_language_has_every_sms_key_with_the_same_placeholders():
    assert set(sms_t.TEXTS) == set(LANGUAGES) == set(sms_t.DAYS_SHORT) == set(sms_t.DAYS_LONG) == set(sms_t.MONTHS)
    da = sms_t.TEXTS["da"]
    for lang, table in sms_t.TEXTS.items():
        assert set(table) == set(da), lang
        for key, text in table.items():
            assert set(_PLACEHOLDER.findall(text)) == set(_PLACEHOLDER.findall(da[key])), f"{lang}.{key}"
        assert len(sms_t.DAYS_SHORT[lang]) == len(sms_t.DAYS_LONG[lang]) == 7 and len(sms_t.MONTHS[lang]) == 12


def test_every_mail_builds_in_every_language_and_stays_in_it():
    for lang in LANGUAGES:
        mails = [tpl.verify("https://x/v", lang=lang), tpl.reset("https://x/r", lang=lang),
                 tpl.invitation("Hansen VVS", "Mads", "staff", "https://x/i", lang=lang),
                 tpl.new_lead("Hansen VVS", "", "", "https://x/l", lang=lang),
                 tpl.daily_report("S", "Title\n\nX: 1", "https://x/d", lang=lang),
                 tpl.ambassador_parent("Lone", "Mads Jensen", "m@x.dk", "https://x/p", "R", "500 kr.", "10 %", 12, lang=lang),
                 tpl.ambassador_approved("Mads", "https://x/a", "MADS42", "https://x/amb", lang=lang),
                 tpl.ambassador_rejected("Mads", "", lang=lang),
                 tpl.ambassador_paid("Mads", "724,25 kr.", "5678", 1001, True, "https://x", lang=lang),
                 tpl.social_drafts_waiting([("Facebook", "Booking")], "https://x/s", lang=lang),
                 tpl.from_plain("S", "Body", lang=lang)]
        for m in mails:
            h = m.html()
            assert f'<html lang="{lang}">' in h and m.heading in h and tx.t(lang, "regards") in m.text()
            assert tx.t(lang, "company_line") in m.text()
            back = tpl.from_payload({"to_email": "a@b.dk", "email": tpl.to_payload(m)})
            assert back.html() == h and back.lang == lang
        if lang != "da":
            text = "\n".join(m.text() for m in mails)
            for danish in ("Venlig hilsen", "Du får denne e-mail", "Virker knappen ikke", "Bekræft"):
                assert danish not in text, f"{lang}: Danish {danish!r} left"


# --- Danish is unchanged ---------------------------------------------------------------------------------------------

def test_danish_output_is_unchanged():
    m = tpl.reset("https://x/r")
    assert m.text() == (
        "Nulstil din adgangskode\n\nVi har fået en anmodning om at nulstille adgangskoden til din Dialogbot-konto. "
        "Klik på knappen for at vælge en ny.\n\nVælg ny adgangskode: https://x/r\n\nLinket virker i 1 time og kan kun "
        "bruges én gang. Har du ikke bedt om det, kan du se bort fra denne e-mail – din adgangskode forbliver uændret.\n\n"
        "Venlig hilsen\nDialogbot\n\n—\nDu får denne e-mail, fordi du har en konto hos Dialogbot.\n"
        "Dialogbot · CVR-nr. 25632710 · Abildgade 18, 8200 Aarhus · dialogbot.dk\n")
    h = tpl.verify("https://x").html()
    assert '<html lang="da">' in h and "Trin 1" in h and "Virker knappen ikke? Kopiér dette link ind i din browser:<br>" in h
    assert tpl.verify("https://x").subject == "Bekræft din e-mail hos Dialogbot"
    inv = tpl.invitation("Hansen VVS", "Mads", "staff", "https://x")
    assert inv.subject == "Mads har inviteret dig til Hansen VVS på Dialogbot" and inv.preheader == "Du er inviteret som medarbejder."
    paid = tpl.ambassador_paid("Mads", "1 kr.", None, 3, False, "https://x")
    assert paid.paragraphs[0] == "Vi har overført 1 kr. til din bankkonto. Pengene er normalt på kontoen inden for 1–2 bankdage."
    assert tpl.from_payload({}).subject == "Besked fra Dialogbot"
    for key, text in sms_t.samples().items():
        assert text.endswith("Vh Hansen VVS"), key
    assert sms_t.call_back("Hansen VVS") == ("Tak for din henvendelse til Hansen VVS. En medarbejder ringer tilbage på "
                                             "dette nummer. Vh Hansen VVS")


def test_danish_report_summary_is_unchanged():
    from app.modules.reports.service import _summary_subject, _summary_text

    d = {"date": "2026-10-27", "conversations": {"started": 14, "visitor_messages": 52},
         "ai": {"ok": 49, "refused": 1, "error": 0}, "leads": {"new": 1, "approved": 3, "approved_fee_net_minor": 123456,
                                                             "new_items": [{"contact_name": "", "need_summary": "X"}]},
         "tasks": {"created": 5, "completed": 4, "open_overdue_at_end": 0}}
    assert _summary_text("Hansen VVS", d) == (
        "Dagsrapport for Hansen VVS – 2026-10-27\n\nSamtaler: 14 (kundebeskeder: 52)\nAI-svar: 49 ok, 1 afvist, 0 fejl\n"
        "Nye henvendelser: 1\nGodkendte henvendelser: 3 (1.234,56 kr. ekskl. moms)\nOpgaver: 5 oprettet, 4 løst, "
        "0 åbne over frist\n\nNye henvendelser:\n- (uden navn): X")
    assert _summary_subject("Hansen VVS", datetime(2026, 10, 27).date()) == "Dagsrapport 2026-10-27 – Hansen VVS"
    en = _summary_text("Hansen VVS", d, "en")
    assert "Approved enquiries: 3 (DKK 1,234.56 excl. VAT)" in en and "- (no name): X" in en
    mail = tpl.daily_report(_summary_subject("Hansen VVS", datetime(2026, 10, 27).date(), "en"), en, "https://x", lang="en")
    assert mail.subject == "Daily report 2026-10-27 – Hansen VVS"
    assert ("Tasks", "5 created, 4 completed, 0 open and overdue") in mail.rows
    assert not any(k.startswith("AI replies") for k, _ in mail.rows) and "AI replies" not in mail.text()


# --- specific languages ----------------------------------------------------------------------------------------------

def test_german_verify_mail_is_formal_german():
    m = tpl.verify("https://www.dialogbot.dk/verify-email?token=a", lang="de")
    assert m.subject == "Bestätigen Sie Ihre E-Mail-Adresse bei Dialogbot"
    assert m.heading == "Willkommen bei Dialogbot" and m.button_label == "E-Mail-Adresse bestätigen"
    t = m.text()
    assert "Mit freundlichen Grüßen" in t and "Schritt 1" in m.html() and '<html lang="de">' in m.html()
    assert "E-Mail-Adresse bestätigen: https://www.dialogbot.dk/verify-email?token=a" in t
    assert " du " not in t and " dein" not in t.lower()  # Sie, never du
    assert "Funktioniert die Schaltfläche nicht?" in m.html()


def test_english_daily_report_subject_and_unknown_language_falls_back_to_danish():
    assert tx.t("en", "report_subject", date="2026-10-27", workspace="Hansen VVS") == "Daily report 2026-10-27 – Hansen VVS"
    assert tpl.verify("https://x", lang="xx").subject == tpl.verify("https://x").subject
    assert tpl.verify("https://x", lang="en-GB").subject == "Confirm your e-mail address for Dialogbot"
    assert tpl.invitation("W", "M", "admin", "https://x", lang="fr").preheader == "Vous êtes invité en tant que administrateur."


def test_caller_sms_in_every_language_is_one_segment_and_signed_by_the_business():
    for lang in LANGUAGES:
        for key, text in sms_t.samples(lang).items():
            assert len(text) <= sms_t.SEGMENT, f"{lang}.{key}: {len(text)} tegn"
            assert text.rstrip().endswith("Hansen VVS"), f"{lang}.{key}"
            assert "Dialogbot" not in text and "http" not in text, f"{lang}.{key}"
    start = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    from app.modules.bookings.service import label

    assert sms_t.when(start, "Europe/Copenhagen", "da") == label(start, "Europe/Copenhagen")
    assert sms_t.when(start, "Europe/Copenhagen", "en") == "Tuesday 3 November at 10:00"
    assert sms_t.when(start, "Europe/Copenhagen", "de") == "Dienstag, 3. November um 10:00 Uhr"
    assert sms_t.booking("Hansen VVS", "", "Inspection", "x", "en") == "Your appointment at Hansen VVS: Inspection, x. Kind regards, Hansen VVS"


# --- who gets which language (database) ------------------------------------------------------------------------------

def _set_ws_lang(db, ws: str, **values):
    db.execute(update(LanguageSettings).where(LanguageSettings.workspace_id == uuid.UUID(ws)).values(**values))
    db.commit()


def test_account_mails_follow_the_users_interface_language(api, db):
    from app.modules.identity import service as identity
    from app.worker import runner

    api.register("anna@testmail.dk")
    db.execute(update(User).where(User.email_normalized == "anna@testmail.dk").values(interface_language="de"))
    db.commit()
    identity.request_password_reset(db, "anna@testmail.dk")
    db.commit()
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.password_reset"))
    assert ev.payload["lang"] == "de"
    old = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.verify_address"))
    assert old.payload.get("lang") == "da"  # registered while Danish
    runner.drain()
    db.expire_all()
    subjects = {d.subject for d in db.scalars(select(EmailDelivery))}
    assert "Setzen Sie Ihr Passwort bei Dialogbot zurück" in subjects
    assert "Bekræft din e-mail hos Dialogbot" in subjects


def test_invitation_follows_the_workspace_interface_language(api, two_workspaces, db):
    from app.worker import runner

    _set_ws_lang(db, two_workspaces["ws_a"], interface_language="sv")
    r = api.invite(two_workspaces["tok_a"], two_workspaces["ws_a"], "ny@testmail.dk")
    assert r.status_code in (200, 201), r.text
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.invitation"))
    assert ev.payload["lang"] == "sv"
    runner.drain()
    db.expire_all()
    d = db.scalar(select(EmailDelivery).where(EmailDelivery.outbox_event_id == ev.id))
    assert d is not None and "har bjudit in dig till Fjord Gulvservice ApS" in d.subject


def test_daily_report_and_new_lead_follow_each_recipients_language(two_workspaces, db):
    from app.models import Lead
    from app.modules.leads import service as leads
    from app.modules.reports import service as reports

    ws = uuid.UUID(two_workspaces["ws_a"])
    db.execute(update(Workspace).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db.execute(update(User).where(User.email_normalized == "owner-a@testmail.dk").values(interface_language="en"))
    db.commit()
    reports.run_due(db, now=datetime(2026, 9, 25, 5, 5, tzinfo=UTC))
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.daily_report",
                                             OutboxEvent.workspace_id == ws))
    assert ev.payload["lang"] == "en"
    assert ev.payload["subject"] == "Daily report 2026-09-24 – Fjord Gulvservice ApS"
    assert ev.payload["body"].startswith("Daily report for Fjord Gulvservice ApS – 2026-09-24")
    other = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.daily_report",
                                                OutboxEvent.workspace_id == uuid.UUID(two_workspaces["ws_b"])))
    assert other.payload["subject"].startswith("Dagsrapport ")  # owner B kept Danish
    lead = Lead(workspace_id=ws, source="manual", contact_name="Mette", need_summary="Gulv")
    db.add(lead)
    db.flush()
    leads._notify_new_lead(db, lead)
    db.commit()
    ev = db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "email.new_lead"))
    assert ev.payload["lang"] == "en"


def test_caller_sms_follows_the_workspace_conversation_language(two_workspaces, db):
    from app.modules.integrations.connectors import sms
    from app.modules.integrations.connectors.base import RunContext

    ws_id = uuid.UUID(two_workspaces["ws_a"])
    ws = db.get(Workspace, ws_id)
    ctx = RunContext(workspace_id=ws_id, channel="phone", caller_phone="+4520304050")
    assert sms.render(db, ws, "ring_tilbage", ctx).startswith("Tak for din henvendelse til Fjord Gulvservice ApS")
    _set_ws_lang(db, two_workspaces["ws_a"], default_conversation_language="de", interface_language="da")
    text = sms.render(db, ws, "ring_tilbage", ctx)
    assert text == ("Vielen Dank für Ihre Anfrage an Fjord Gulvservice ApS. Wir rufen Sie unter dieser Nummer zurück. "
                    "Freundliche Grüße, Fjord Gulvservice ApS")
