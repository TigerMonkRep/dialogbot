"""Branded system emails: one layout for every email Dialogbot sends, as HTML plus a plain-text twin.

Each email is built from the same few parts – a heading, short paragraphs, an optional button and an optional
note in small print – so the look and tone stay consistent. The HTML uses tables and inline styles only, because
that is what email clients (Outlook, Gmail, Apple Mail) render reliably. Every value is escaped.

Brand (docs/brand.md, "Byggevejledningen"): a white card with a 2 px ink outline on the panel background, a blue
button, the blue mark with the chat bubble, and a yellow step square when the mail is a step in the set-up.

Rules every mail follows: one heading, a few short paragraphs, ONE button (the single next step), small print last.
A new mail is a function that returns an `Email` and is added to `samples()`; it then inherits the layout, the dark
mode and the mobile layout below, and `tests/test_email_templates.py` fails until it is listed (so it also shows up in
`python -m scripts.preview_emails`).

Light is the default and is written inline (all clients render it). Dark mode and the phone layout are a `<style>`
block with `!important` overrides: Apple Mail, Outlook.com/app, iOS Mail and Samsung Mail honour it; Gmail on Android
ignores it and may apply its own colour inversion, which is why the colours below are plain brand tokens with good
contrast either way.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from app.config import get_settings

INK = "#14213D"
INK_SOFT = "#3C4659"
PAPER = "#FFFFFF"
PANEL = "#EEF4FB"
ACCENT = "#2456F6"
HIGHLIGHT = "#FFCF3F"
MUTED = "#5B6475"
LINE = "#D6DEEA"
FONT = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
HEAD_FONT = "Outfit,Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
# The mark served by the website (the icon is the brand mark: blue rounded square with the chat bubble).
LOGO_PATH = "/icons/icon-192.png"

# Dark mode (docs/brand.md has one surface colour, ink; the card is ink, the page one step darker).
DARK_PAGE = "#0D1630"
DARK_CARD = INK
DARK_BORDER = "#4A5A82"
DARK_TEXT = "#D3DBEC"
DARK_MUTED = "#98A4BD"
DARK_LINK = "#9DB8FF"

CSS = f"""
:root {{ color-scheme: light dark; supported-color-schemes: light dark; }}
@media (prefers-color-scheme: dark) {{
  .pg {{ background:{DARK_PAGE} !important; }}
  .card {{ background:{DARK_CARD} !important; border-color:{DARK_BORDER} !important; }}
  .hd, .wm {{ color:#FFFFFF !important; }}
  .tx {{ color:{DARK_TEXT} !important; }}
  .tx b, .tx strong {{ color:#FFFFFF !important; }}
  .mt, .mt a {{ color:{DARK_MUTED} !important; }}
  .lk {{ color:{DARK_LINK} !important; }}
  .panel {{ background:#1B2A4C !important; border-color:{DARK_BORDER} !important; }}
}}
@media only screen and (max-width:480px) {{
  .pg {{ padding:16px 10px !important; }}
  .pad {{ padding:24px 20px 8px !important; }}
  .h1 {{ font-size:23px !important; }}
  .btnt {{ width:100% !important; }}
  .btna {{ display:block !important; text-align:center !important; }}
  .rl, .rv {{ display:block !important; width:100% !important; text-align:left !important; padding:2px 0 !important; }}
  .rv {{ padding-bottom:10px !important; }}
}}
"""

# Sender identity in every footer (e-handelsloven § 7: name, CVR and address).
COMPANY_LINE = "Dialogbot · CVR-nr. 25632710 · Abildgade 18, 8200 Aarhus"

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
    step: int | None = None  # set when the mail is a step in the set-up: a yellow step square above the heading
    rows: list[tuple[str, str]] = field(default_factory=list)  # label/value facts shown in a panel (the day's numbers)

    def text(self) -> str:
        parts = [self.heading, ""]
        if self.rows:
            parts += [*[f"{k}: {v}" for k, v in self.rows], ""]
        parts += [p for para in self.paragraphs for p in (para, "")]
        if self.button_url:
            parts += [f"{self.button_label or 'Åbn'}: {self.button_url}", ""]
        if self.note:
            parts += [self.note, ""]
        parts += ["Venlig hilsen", "Dialogbot", "", "—", self.footer_reason, f"{COMPANY_LINE} · dialogbot.dk"]
        return "\n".join(parts).strip() + "\n"

    def html(self) -> str:
        base = get_settings().frontend_base_url.rstrip("/")
        logo = f"{base}{LOGO_PATH}"
        e = html.escape
        paras = "".join(
            f'<p class="tx" style="margin:0 0 16px;font:16px/1.6 {FONT};color:{INK_SOFT};">'
            f'{e(p).replace(chr(10), "<br>")}</p>' for p in self.paragraphs)
        panel = ""
        if self.rows:
            trs = "".join(
                f'<tr><td class="mt rl" style="padding:6px 12px 6px 0;font:14px/1.4 {FONT};color:{MUTED};">{e(k)}</td>'
                f'<td class="hd rv" align="right" style="padding:6px 0;font:800 16px/1.4 {HEAD_FONT};color:{INK};">{e(v)}</td></tr>'
                for k, v in self.rows)
            panel = (f'<table class="panel" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                     f'style="margin:0 0 20px;background:{PANEL};border:1.5px solid {LINE};border-radius:14px;">'
                     f'<tr><td style="padding:10px 16px;"><table role="presentation" width="100%" cellpadding="0" '
                     f'cellspacing="0" border="0">{trs}</table></td></tr></table>')
        button = ""
        if self.button_url:
            button = (
                f'<table class="btnt" role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px;">'
                f'<tr><td style="border-radius:14px;background:{ACCENT};">'
                f'<a class="btna" href="{e(self.button_url, quote=True)}" style="display:inline-block;padding:16px 26px;'
                f'font:600 16px/1 {FONT};color:#ffffff;text-decoration:none;border-radius:14px;">'
                f'{e(self.button_label or "Åbn")}</a></td></tr></table>'
                f'<p class="mt" style="margin:0 0 16px;font:13px/1.5 {FONT};color:{MUTED};">Virker knappen ikke? Kopiér '
                f'dette link ind i din browser:<br><a class="lk" href="{e(self.button_url, quote=True)}" '
                f'style="color:{ACCENT};word-break:break-all;">{e(self.button_url)}</a></p>')
        note = (f'<p class="mt" style="margin:0 0 16px;font:13px/1.5 {FONT};color:{MUTED};">{e(self.note)}</p>'
                if self.note else "")
        pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{e(self.preheader)}</div>'
               if self.preheader else "")
        step = ""
        if self.step:  # the yellow step square from the building guide (stays yellow with ink text in dark mode)
            step = (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px;">'
                    f'<tr><td width="48" height="48" align="center" valign="middle" style="width:48px;height:48px;'
                    f'border-radius:12px;background:{HIGHLIGHT};font:800 24px/48px {HEAD_FONT};color:{INK};">'
                    f'{self.step}</td><td class="mt" style="padding-left:12px;font:600 12px/1 {FONT};'
                    f'letter-spacing:0.12em;text-transform:uppercase;color:{MUTED};">Trin {self.step}</td></tr></table>')
        return f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>{e(self.subject)}</title><style>{CSS}</style></head>
<body class="pg" style="margin:0;padding:0;background:{PANEL};">{pre}
<table class="pg" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PANEL};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;">
<tr><td style="padding:0 4px 20px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="vertical-align:middle;"><img src="{e(logo, quote=True)}" width="36" height="36" alt="" style="display:block;border:0;border-radius:10px;"></td>
<td class="wm" style="vertical-align:middle;padding-left:10px;font:800 22px/1 {HEAD_FONT};color:{INK};letter-spacing:-0.3px;">Dialogbot</td>
</tr></table></td></tr>
<tr><td class="card" style="background:{PAPER};border:2px solid {INK};border-radius:20px;">
<div class="pad" style="padding:32px 32px 16px;">
{step}<h1 class="hd h1" style="margin:0 0 20px;font:800 26px/1.25 {HEAD_FONT};color:{INK};letter-spacing:-0.3px;">{e(self.heading)}</h1>
{panel}{paras}{button}{note}
<p class="tx" style="margin:8px 0 16px;font:16px/1.6 {FONT};color:{INK_SOFT};">Venlig hilsen<br><strong class="hd" style="color:{INK};">Dialogbot</strong></p>
</div></td></tr>
<tr><td class="mt" style="padding:20px 8px 0;font:12px/1.6 {FONT};color:{MUTED};text-align:center;">
{e(self.footer_reason)}<br>{e(COMPANY_LINE)} · <a href="{e(base, quote=True)}" style="color:{MUTED};">dialogbot.dk</a>
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
        step=1,
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
        paragraphs=[f"{invited_by} har inviteret dig til {workspace} på Dialogbot som {ROLE_DA.get(role, role)}. "
                    "Som medlem kan du se henvendelser, samtaler og opgaver."],
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
    """The day's numbers as a small panel, then who called. Internal counters (AI answers) stay in the app."""
    lines = body.split("\n")
    heading = lines[0] if lines else subject
    blocks = [b.strip() for b in re.split(r"\n\s*\n", "\n".join(lines[1:]).strip()) if b.strip()]
    rows: list[tuple[str, str]] = []
    paragraphs: list[str] = []
    for b in blocks:
        facts = [ln.split(": ", 1) for ln in b.split("\n") if ": " in ln and not ln.startswith("- ")]
        if not rows and facts and len(facts) == len(b.split("\n")):
            rows = [(k, v) for k, v in facts if not k.startswith("AI-svar")]
        else:
            paragraphs.append(b)
    return Email(subject=subject, heading=heading, paragraphs=paragraphs, rows=rows,
                 preheader="Gårsdagens henvendelser, samtaler og opgaver.",
                 button_label="Se hele rapporten" if link else None, button_url=link,
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
        subject="Velkommen som Dialogbot-ambassadør",
        preheader=f"Dit personlige link og din kode {code} er klar.",
        heading=f"Velkommen som ambassadør, {first_name}",
        paragraphs=["Du er godkendt. Del dit personlige link med virksomheder, du kender:",
                    f"{link}\nDin kode: {code}",
                    "Rabat, bonus, saldo og færdige tekster ligger på din side. Skriv altid, at det er reklame, og at "
                    "du får bonus – og send kun til folk, du kender."],
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
            "footer_reason": mail.footer_reason, "preheader": mail.preheader, "step": mail.step,
            "rows": [list(r) for r in mail.rows]}


def from_payload(p: dict) -> Email:
    """A structured payload (`email` key) or an older free-text one (`subject` + `body`)."""
    if isinstance(p.get("email"), dict):
        data = {k: v for k, v in p["email"].items() if k in Email.__dataclass_fields__}
        data["rows"] = [(str(k), str(v)) for k, v in data.get("rows") or []]
        return Email(**data)
    return from_plain(p.get("subject") or "Besked fra Dialogbot", p.get("body") or "")


# --------------------------------------------------------------------------- the registry

def samples() -> dict[str, Email]:
    """One realistic example of every mail Dialogbot sends, keyed by the builder's name.

    Used by `python -m scripts.preview_emails` and the dev page. A new builder that returns an `Email` must be added
    here; `tests/test_email_templates.py` checks it."""
    return {
        "verify": verify("https://www.dialogbot.dk/verify-email?token=eksempel"),
        "reset": reset("https://www.dialogbot.dk/password/reset?token=eksempel"),
        "invitation": invitation("Hansen VVS", "Mads Jensen", "staff", "https://www.dialogbot.dk/invite/eksempel"),
        "new_lead": new_lead("Hansen VVS", "Mette Nielsen", "Utæt vandhane i køkkenet – haster lidt",
                             "https://www.dialogbot.dk/app/leads/eksempel"),
        "daily_report": daily_report(
            "Dagsrapport 2026-10-27 – Hansen VVS",
            "Dagsrapport for Hansen VVS – 2026-10-27\n\nSamtaler: 14 (kundebeskeder: 52)\nAI-svar: 49 ok, 1 afvist, 0 fejl\n"
            "Nye henvendelser: 5\nGodkendte henvendelser: 3 (447 kr. ekskl. moms)\nOpgaver: 5 oprettet, 4 løst, "
            "0 åbne over frist\n\nNye henvendelser:\n- Mette Nielsen: Utæt vandhane i køkkenet\n"
            "- Jens Poulsen: Tilbud på nyt badeværelse", "https://www.dialogbot.dk/app/reports?date=2026-10-27"),
        "ambassador_parent": ambassador_parent("Lone", "Mads Jensen", "mads@example.dk",
                                               "https://www.dialogbot.dk/ambassador/parent/eksempel",
                                               "- Skriv altid, at det er reklame\n- Send kun til folk, du kender",
                                               "500 kr.", "10 %", 12),
        "ambassador_approved": ambassador_approved("Mads", "https://www.dialogbot.dk/a/mads", "MADS42",
                                                   "https://www.dialogbot.dk/ambassador"),
        "ambassador_rejected": ambassador_rejected("Mads", ""),
        "ambassador_paid": ambassador_paid("Mads", "724,25 kr.", "5678", 1001, True,
                                           "https://www.dialogbot.dk/ambassador"),
        "from_plain": from_plain("Gammel besked", "Hej Mads\n\nTekst her.\n\nSe det her: https://www.dialogbot.dk/x\n\n"
                                                  "Venlig hilsen\nDialogbot"),
    }
