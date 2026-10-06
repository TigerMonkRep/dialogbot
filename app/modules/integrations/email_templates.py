"""Branded system emails: one layout for every email Dialogbot sends, as HTML plus a plain-text twin.

Each email is built from the same few parts – a heading, short paragraphs, an optional button and an optional
note in small print – so the look and tone stay consistent. The HTML uses tables and inline styles only, because
that is what email clients (Outlook, Gmail, Apple Mail) render reliably. Every value is escaped.

Brand: dark green #164e43, lime #d8ee86, mint background #e7fef9, the headset logo from the website.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from app.config import get_settings

GREEN = "#164e43"
LIME = "#d8ee86"
MINT = "#e7fef9"
INK = "#12302a"
MUTED = "#4f6862"
LINE = "#d5e4df"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

ROLE_DA = {"owner": "ejer", "admin": "administrator", "staff": "medarbejder", "reader": "læser"}


@dataclass
class Email:
    subject: str
    heading: str
    paragraphs: list[str] = field(default_factory=list)  # plain text; a line break inside one is kept
    button_label: str | None = None
    button_url: str | None = None
    note: str | None = None  # small print under the button, e.g. "Linket udløber om 1 time"
    footer_reason: str = "Du får denne e-mail, fordi du har en konto hos Dialogbot."
    preheader: str | None = None  # the preview line shown next to the subject in the inbox

    def text(self) -> str:
        parts = [self.heading, "", *[p for para in self.paragraphs for p in (para, "")]]
        if self.button_url:
            parts += [f"{self.button_label or 'Åbn'}: {self.button_url}", ""]
        if self.note:
            parts += [self.note, ""]
        parts += ["Venlig hilsen", "Dialogbot", "", "—", self.footer_reason, "Dialogbot · dialogbot.dk"]
        return "\n".join(parts).strip() + "\n"

    def html(self) -> str:
        base = get_settings().frontend_base_url.rstrip("/")
        logo = f"{base}/icons/icon-192.png"
        e = html.escape
        paras = "".join(
            f'<p style="margin:0 0 16px;font:16px/1.6 {FONT};color:{INK};">{e(p).replace(chr(10), "<br>")}</p>'
            for p in self.paragraphs)
        button = ""
        if self.button_url:
            button = (
                f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px;">'
                f'<tr><td style="border-radius:10px;background:{GREEN};">'
                f'<a href="{e(self.button_url, quote=True)}" style="display:inline-block;padding:14px 26px;'
                f'font:600 16px/1 {FONT};color:#ffffff;text-decoration:none;border-radius:10px;">'
                f'{e(self.button_label or "Åbn")}</a></td></tr></table>'
                f'<p style="margin:0 0 16px;font:13px/1.5 {FONT};color:{MUTED};">Virker knappen ikke? Kopiér dette link '
                f'ind i din browser:<br><a href="{e(self.button_url, quote=True)}" style="color:{GREEN};'
                f'word-break:break-all;">{e(self.button_url)}</a></p>')
        note = (f'<p style="margin:0 0 16px;font:13px/1.5 {FONT};color:{MUTED};">{e(self.note)}</p>'
                if self.note else "")
        pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{e(self.preheader)}</div>'
               if self.preheader else "")
        return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{e(self.subject)}</title></head>
<body style="margin:0;padding:0;background:{MINT};">{pre}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{MINT};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;">
<tr><td style="padding:0 4px 20px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="vertical-align:middle;"><img src="{e(logo, quote=True)}" width="36" height="36" alt="" style="display:block;border:0;border-radius:9px;"></td>
<td style="vertical-align:middle;padding-left:10px;font:800 20px/1 {FONT};color:{GREEN};letter-spacing:-0.01em;">Dialogbot</td>
</tr></table></td></tr>
<tr><td style="background:#ffffff;border:1px solid {LINE};border-radius:16px;overflow:hidden;">
<div style="height:6px;background:{LIME};line-height:6px;font-size:0;">&nbsp;</div>
<div style="padding:32px 32px 16px;">
<h1 style="margin:0 0 20px;font:800 24px/1.3 {FONT};color:{GREEN};">{e(self.heading)}</h1>
{paras}{button}{note}
<p style="margin:8px 0 16px;font:16px/1.6 {FONT};color:{INK};">Venlig hilsen<br><strong>Dialogbot</strong></p>
</div></td></tr>
<tr><td style="padding:20px 8px 0;font:12px/1.6 {FONT};color:{MUTED};text-align:center;">
{e(self.footer_reason)}<br>Dialogbot · <a href="{e(base, quote=True)}" style="color:{MUTED};">dialogbot.dk</a>
</td></tr>
</table></td></tr></table></body></html>"""


_URL = re.compile(r"(https?://\S+)")


def from_plain(subject: str, body: str, footer_reason: str | None = None) -> Email:
    """Wrap an older free-text email (subject + body) in the branded layout.

    A greeting line becomes the heading, a closing "Venlig hilsen …" is dropped (the layout adds its own), and the
    first stand-alone link or "Label: link" line becomes the button."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body.strip()) if b.strip()]
    heading = subject
    if blocks and re.match(r"^(Hej|Kære)\b", blocks[0]) and "\n" not in blocks[0]:
        heading = blocks.pop(0).rstrip(",")
    if blocks and blocks[-1].lower().startswith("venlig hilsen"):
        blocks.pop()
    button_label = button_url = None
    kept: list[str] = []
    for b in blocks:
        m = re.fullmatch(r"(?:(.{2,60}?):\s*)?(https?://\S+)", b)
        if button_url is None and m:
            button_label, button_url = (m.group(1) or "Åbn").strip(), m.group(2)
            continue
        if button_url is None and "\n" in b:
            lines = b.split("\n")
            if _URL.fullmatch(lines[-1].strip()):
                button_url = lines[-1].strip()
                button_label = "Åbn"
                b = "\n".join(lines[:-1]).strip()
        kept.append(b)
    return Email(subject=subject, heading=heading, paragraphs=kept, button_label=button_label, button_url=button_url,
                 footer_reason=footer_reason or "Du får denne e-mail, fordi du har en konto hos Dialogbot.")


# --------------------------------------------------------------------------- the emails

def verify(link: str) -> Email:
    return Email(
        subject="Bekræft din e-mail hos Dialogbot",
        preheader="Ét klik, så er din konto klar.",
        heading="Velkommen til Dialogbot",
        paragraphs=["Tak, fordi du har oprettet en konto. Bekræft din e-mailadresse, så kan du komme i gang med at "
                    "sætte din AI-receptionist op."],
        button_label="Bekræft min e-mail", button_url=link,
        note="Linket virker i 48 timer. Har du ikke oprettet en konto hos Dialogbot, kan du se bort fra denne e-mail.",
        footer_reason="Du får denne e-mail, fordi nogen har oprettet en konto hos Dialogbot med din adresse.")


def reset(link: str) -> Email:
    return Email(
        subject="Nulstil din adgangskode hos Dialogbot",
        preheader="Vælg en ny adgangskode – linket virker i 1 time.",
        heading="Nulstil din adgangskode",
        paragraphs=["Vi har fået en anmodning om at nulstille adgangskoden til din Dialogbot-konto. Klik på knappen "
                    "for at vælge en ny."],
        button_label="Vælg ny adgangskode", button_url=link,
        note="Linket virker i 1 time og kan kun bruges én gang. Har du ikke bedt om det, kan du se bort fra denne "
             "e-mail – din adgangskode forbliver uændret.")


def invitation(workspace: str, invited_by: str, role: str, link: str) -> Email:
    return Email(
        subject=f"{invited_by} har inviteret dig til {workspace} på Dialogbot",
        preheader=f"Du er inviteret som {ROLE_DA.get(role, role)}.",
        heading=f"Du er inviteret til {workspace}",
        paragraphs=[f"{invited_by} har inviteret dig til at være med i {workspace} på Dialogbot som "
                    f"{ROLE_DA.get(role, role)}.",
                    "Dialogbot er en AI-receptionist, der tager telefonen og svarer på hjemmesiden, når I selv har "
                    "travlt. Som medlem kan du se henvendelser, samtaler og opgaver."],
        button_label="Acceptér invitationen", button_url=link,
        note="Invitationen virker i 72 timer. Har du ikke en konto endnu, opretter du den undervejs.",
        footer_reason=f"Du får denne e-mail, fordi {invited_by} har inviteret dig til Dialogbot.")


def new_lead(workspace: str, contact_name: str, need: str, link: str) -> Email:
    name = contact_name or "En kunde"
    return Email(
        subject=f"Ny henvendelse: {name}",
        preheader=need[:90] if need else f"{name} vil gerne kontaktes.",
        heading="Ny henvendelse",
        paragraphs=[f"{name} vil gerne kontaktes af {workspace}.", f"Behov: {need or '(ikke angivet)'}"],
        button_label="Se henvendelsen", button_url=link,
        footer_reason=f"Du får denne e-mail, fordi du er tilknyttet {workspace} på Dialogbot.")


def daily_report(subject: str, body: str, link: str | None) -> Email:
    lines = [ln for ln in body.split("\n")]
    heading = lines[0] if lines else subject
    rest = "\n".join(lines[1:]).strip()
    paragraphs = [b.strip() for b in re.split(r"\n\s*\n", rest) if b.strip()]
    return Email(subject=subject, heading=heading, paragraphs=paragraphs, preheader="Gårsdagens henvendelser, "
                 "samtaler og opgaver.", button_label="Se hele rapporten" if link else None, button_url=link,
                 footer_reason="Du får denne e-mail, fordi dagsrapporten er slået til for jeres arbejdsrum. Du kan "
                               "slå den fra under Rapporter.")


# --------------------------------------------------------------------------- ambassador programme

def ambassador_parent(parent_name: str, ambassador_name: str, ambassador_email: str, link: str, rules: str,
                      bonus: str, share: str, months: int) -> Email:
    first = ambassador_name.split()[0]
    return Email(
        subject=f"{first} vil være ambassadør for Dialogbot – vil du godkende?",
        preheader=f"{first} er under 18, så vi har brug for din godkendelse, før vi udbetaler bonus.",
        heading=f"Hej {parent_name}",
        paragraphs=[f"{ambassador_name} ({ambassador_email}) har meldt sig som ambassadør for Dialogbot. Som "
                    "ambassadør anbefaler man Dialogbot – en dansk AI-receptionist – til virksomheder, man kender, og "
                    "får en bonus, når de bliver betalende kunder.",
                    f"Bonussen er {bonus} pr. ny kunde plus {share} af det, kunden betaler, i {months} måneder. Den "
                    "udbetales til " + first + "s bankkonto som B-indkomst, som vi indberetter til Skattestyrelsen. "
                    "Der trækkes ikke skat.",
                    f"Fordi {first} er under 18, udbetaler vi først, når du har godkendt aftalen. {first} kan godt "
                    "dele sit link imens.",
                    f"Reglerne {first} har sagt ja til:\n{rules}"],
        button_label="Læs og godkend aftalen", button_url=link,
        note="Har du spørgsmål, eller vil du ikke godkende, så svar bare på denne e-mail.",
        footer_reason=f"Du får denne e-mail, fordi {ambassador_name} har oplyst dig som forælder eller værge.")


def ambassador_approved(first_name: str, link: str, code: str, portal: str) -> Email:
    return Email(
        subject="Velkommen som Dialogbot-ambassadør 🎉",
        preheader=f"Dit personlige link og din kode {code} er klar.",
        heading=f"Velkommen som ambassadør, {first_name}!",
        paragraphs=["Du er godkendt. Nu kan du begynde at anbefale Dialogbot til virksomheder, du kender.",
                    f"Dit personlige link:\n{link}",
                    f"Din kode: {code}",
                    "Når en virksomhed opretter sig via dit link eller med din kode, får de 50 % rabat på første "
                    "måned – og du får din bonus, når de har betalt. På din side kan du følge dine kunder og din "
                    "saldo og finde færdige tekster, du kan dele.",
                    "Husk reglerne: skriv altid, at det er reklame, og at du får bonus, og send kun beskeder til folk, "
                    "du kender."],
        button_label="Gå til min ambassadørside", button_url=portal,
        footer_reason="Du får denne e-mail, fordi du har meldt dig som ambassadør for Dialogbot.")


def ambassador_rejected(first_name: str, note: str) -> Email:
    paras = ["Tak for din interesse i at blive ambassadør for Dialogbot. Vi kan desværre ikke godkende din "
             "tilmelding lige nu."]
    if note:
        paras.append(note)
    paras.append("Har du spørgsmål, så svar bare på denne e-mail.")
    return Email(subject="Din tilmelding som Dialogbot-ambassadør", heading=f"Hej {first_name}", paragraphs=paras,
                 footer_reason="Du får denne e-mail, fordi du har meldt dig som ambassadør for Dialogbot.")


def ambassador_paid(first_name: str, amount: str, bank_last4: str | None, number: int, b_income: bool,
                    portal: str) -> Email:
    paras = [f"Vi har overført {amount} til din bankkonto"
             + (f", der slutter på {bank_last4}" if bank_last4 else "") + ". Pengene er normalt på kontoen inden for "
             "1–2 bankdage.",
             f"Afregningsbilag nr. {number} ligger på din ambassadørside."]
    if b_income:
        paras.append("Beløbet er B-indkomst, og vi indberetter det til Skattestyrelsen. Der er ikke trukket skat, så "
                     "husk at tjekke din forskudsopgørelse.")
    paras.append("Tak, fordi du anbefaler Dialogbot!")
    return Email(subject=f"Din ambassadørbonus på {amount} er på vej", preheader="Se afregningsbilaget på din side.",
                 heading=f"Hej {first_name}, din bonus er på vej", paragraphs=paras,
                 button_label="Se afregningsbilaget", button_url=portal,
                 footer_reason="Du får denne e-mail, fordi du er ambassadør for Dialogbot.")


def to_payload(mail: Email) -> dict:
    """Serialize for the outbox (the worker renders it with `from_payload`)."""
    return {"subject": mail.subject, "heading": mail.heading, "paragraphs": mail.paragraphs,
            "button_label": mail.button_label, "button_url": mail.button_url, "note": mail.note,
            "footer_reason": mail.footer_reason, "preheader": mail.preheader}


def from_payload(p: dict) -> Email:
    """A structured payload (`email` key) or an older free-text one (`subject` + `body`)."""
    if isinstance(p.get("email"), dict):
        return Email(**{k: v for k, v in p["email"].items() if k in Email.__dataclass_fields__})
    return from_plain(p.get("subject") or "Besked fra Dialogbot", p.get("body") or "")
