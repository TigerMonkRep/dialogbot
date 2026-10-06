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
