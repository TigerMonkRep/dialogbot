"""Branded email layout: every email has HTML and plain text, escapes input, shows the button and logo,
and older free-text payloads still render."""
from __future__ import annotations

from app.modules.integrations import email_templates as tpl


def test_layout_escapes_and_has_text_twin():
    mail = tpl.new_lead("Hansen VVS", "<script>x</script>", "Ny radiator & rør", "https://www.dialogbot.dk/app/leads/1")
    h = mail.html()
    assert "<script>x</script>" not in h and "&lt;script&gt;" in h
    assert "icons/icon-192.png" in h and "Se henvendelsen" in h and "Ny radiator &amp; rør" in h
    t = mail.text()
    assert "Se henvendelsen: https://www.dialogbot.dk/app/leads/1" in t and "Venlig hilsen" in t
    assert "CVR-nr. 25632710" in t and "CVR-nr. 25632710" in mail.html()
    assert "Simuleret" not in t


def test_every_email_builds():
    mails = [tpl.verify("https://x/verify?token=a"), tpl.reset("https://x/reset?token=b"),
             tpl.invitation("Hansen VVS", "Mads", "staff", "https://x/invite/c"),
             tpl.daily_report("Dagsrapport", "Dagsrapport for Hansen\n\nSamtaler: 3", "https://x/r"),
             tpl.ambassador_parent("Lone", "Mads Jensen", "m@x.dk", "https://x/p", "Regler", "500 kr.", "10 %", 12),
             tpl.ambassador_approved("Mads", "https://x/a/mads", "MADS42", "https://x/ambassador"),
             tpl.ambassador_rejected("Mads", ""), tpl.ambassador_paid("Mads", "724,25 kr.", "5678", 1001, True, "https://x")]
    for m in mails:
        assert m.subject and m.heading in m.html() and m.text().strip()
    assert "medarbejder" in mails[2].text()


def test_payload_round_trip_and_old_free_text():
    m = tpl.ambassador_approved("Mads", "https://x/a/mads", "MADS42", "https://x/ambassador")
    back = tpl.from_payload({"to_email": "a@b.dk", "email": tpl.to_payload(m)})
    assert back.html() == m.html()
    old = tpl.from_payload({"subject": "Gammel", "body": "Hej Mads\n\nTekst her.\n\nhttps://x/link\n\nVenlig hilsen\nDialogbot"})
    assert old.heading == "Hej Mads" and old.button_url == "https://x/link" and old.paragraphs == ["Tekst her."]


# --- design v2: one registry, one layout, dark mode, phone layout, one button ---------------------------------------

def test_every_builder_is_in_the_registry_so_new_mails_get_previewed_and_tested():
    import inspect

    builders = {n for n, f in inspect.getmembers(tpl, inspect.isfunction)
                if f.__module__ == tpl.__name__ and not n.startswith("_") and f.__annotations__.get("return") == "Email"
                and n not in ("from_plain", "from_payload")}
    assert builders and builders <= set(tpl.samples()), f"add to samples(): {builders - set(tpl.samples())}"


def test_every_mail_has_dark_mode_phone_layout_one_button_and_no_emoji():
    import re

    for key, mail in tpl.samples().items():
        h = mail.html()
        assert "prefers-color-scheme: dark" in h and "max-width:480px" in h, key
        assert 'name="color-scheme" content="light dark"' in h, key
        assert len(re.findall(r'class="btna"', h)) <= 1, f"{key}: more than one button"
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", mail.subject + mail.text()), f"{key}: emoji"
        assert "#14213D" in h and ("#2456F6" in h or not mail.button_url)           # v2 palette: ink, blue button
        assert "#00362d" not in h.lower() and "#d6ec85" not in h.lower()           # never the old green/lime


def test_report_numbers_are_a_panel_and_internal_counters_stay_in_the_app():
    mail = tpl.samples()["daily_report"]
    assert ("Opgaver", "5 oprettet, 4 løst, 0 åbne over frist") in mail.rows
    assert not any(k.startswith("AI-svar") for k, _ in mail.rows) and "AI-svar" not in mail.text()
    assert "Mette Nielsen" in mail.text() and 'class="panel"' in mail.html()
    back = tpl.from_payload({"to_email": "a@b.dk", "email": tpl.to_payload(mail)})
    assert back.rows == mail.rows and back.html() == mail.html()


def test_the_step_square_is_yellow_with_ink_text_in_both_schemes():
    h = tpl.verify("https://x").html()
    assert "#FFCF3F" in h and h.count("Trin 1") == 1


def test_preview_script_writes_every_mail_and_sms(tmp_path):
    from scripts import preview_emails

    keys = preview_emails.build(tmp_path)
    for k in keys:
        assert (tmp_path / f"{k}.html").exists() and (tmp_path / f"{k}.txt").exists()
        assert "@media all" in (tmp_path / f"{k}.dark.html").read_text(encoding="utf-8")
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Telefon (390 px)" in index and "Vh Hansen VVS" in index
