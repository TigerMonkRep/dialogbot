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
from app.core.languages import normalize
from app.modules.integrations.email_texts import GREETING_WORDS, TEXTS, t

INK = "#14213D"
INK_SOFT = "#3C4659"
PAPER = "#FFFFFF"
PANEL = "#EEF4FB"
ACCENT = "#2456F6"
PRIVAT_ACCENT = "#C4461A"  # docs/brand.md – the Privat orange (white text ≥ 4.5:1)
HIGHLIGHT = "#FFCF3F"
MUTED = "#5B6475"
LINE = "#D6DEEA"
FONT = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
HEAD_FONT = "Outfit,Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
# The mark served by the website (the icon is the brand mark: blue rounded square with the chat bubble).
LOGO_PATH = "/icons/icon-192.png"
PRIVAT_LOGO_PATH = "/icons/privat-icon-192.png"

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

ROLES = {lang: {r: TEXTS[lang][f"role_{r}"] for r in ("owner", "admin", "staff", "reader")} for lang in TEXTS}
ROLE_DA = ROLES["da"]


def _role(role: str, lang: str) -> str:
    return ROLES.get(normalize(lang), ROLE_DA).get(role, role)


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
    lang: str = "da"  # the language of the layout's own words (greeting, button fallback, footer company line)
    audience: str = "erhverv"  # "privat": the Privat orange (#C4461A), the Privat icon and «Dialogbot Privat» in the header

    def text(self) -> str:
        lang = self.lang
        parts = [self.heading, ""]
        if self.rows:
            parts += [*[f"{k}: {v}" for k, v in self.rows], ""]
        parts += [p for para in self.paragraphs for p in (para, "")]
        if self.button_url:
            parts += [f"{self.button_label or t(lang, 'open')}: {self.button_url}", ""]
        if self.note:
            parts += [self.note, ""]
        parts += [t(lang, "regards"), "Dialogbot", "", "—", self.footer_reason, f"{t(lang, 'company_line')} · dialogbot.dk"]
        return "\n".join(parts).strip() + "\n"

    def html(self) -> str:
        lang = normalize(self.lang)
        base = get_settings().frontend_base_url.rstrip("/")
        logo = f"{base}{PRIVAT_LOGO_PATH if self.audience == 'privat' else LOGO_PATH}"
        e = html.escape
        accent = PRIVAT_ACCENT if self.audience == "privat" else ACCENT
        brand = "Dialogbot Privat" if self.audience == "privat" else "Dialogbot"
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
                f'<tr><td style="border-radius:14px;background:{accent};">'
                f'<a class="btna" href="{e(self.button_url, quote=True)}" style="display:inline-block;padding:16px 26px;'
                f'font:600 16px/1 {FONT};color:#ffffff;text-decoration:none;border-radius:14px;">'
                f'{e(self.button_label or t(lang, "open"))}</a></td></tr></table>'
                f'<p class="mt" style="margin:0 0 16px;font:13px/1.5 {FONT};color:{MUTED};">{e(t(lang, "button_fallback"))}'
                f'<br><a class="lk" href="{e(self.button_url, quote=True)}" '
                f'style="color:{accent};word-break:break-all;">{e(self.button_url)}</a></p>')
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
                    f'letter-spacing:0.12em;text-transform:uppercase;color:{MUTED};">{e(t(lang, "step", n=self.step))}</td></tr></table>')
        return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>{e(self.subject)}</title><style>{CSS}</style></head>
<body class="pg" style="margin:0;padding:0;background:{PANEL};">{pre}
<table class="pg" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PANEL};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;">
<tr><td style="padding:0 4px 20px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="vertical-align:middle;"><img src="{e(logo, quote=True)}" width="36" height="36" alt="" style="display:block;border:0;border-radius:10px;"></td>
<td class="wm" style="vertical-align:middle;padding-left:10px;font:800 22px/1 {HEAD_FONT};color:{INK};letter-spacing:-0.3px;">{brand}</td>
</tr></table></td></tr>
<tr><td class="card" style="background:{PAPER};border:2px solid {INK};border-radius:20px;">
<div class="pad" style="padding:32px 32px 16px;">
{step}<h1 class="hd h1" style="margin:0 0 20px;font:800 26px/1.25 {HEAD_FONT};color:{INK};letter-spacing:-0.3px;">{e(self.heading)}</h1>
{panel}{paras}{button}{note}
<p class="tx" style="margin:8px 0 16px;font:16px/1.6 {FONT};color:{INK_SOFT};">{e(t(lang, "regards"))}<br><strong class="hd" style="color:{INK};">Dialogbot</strong></p>
</div></td></tr>
<tr><td class="mt" style="padding:20px 8px 0;font:12px/1.6 {FONT};color:{MUTED};text-align:center;">
{e(self.footer_reason)}<br>{e(t(lang, "company_line"))} · <a href="{e(base, quote=True)}" style="color:{MUTED};">dialogbot.dk</a>
</td></tr>
</table></td></tr></table></body></html>"""


_URL = re.compile(r"(https?://\S+)")


def from_plain(subject: str, body: str, footer_reason: str | None = None, lang: str = "da") -> Email:
    """Wrap an older free-text email (subject + body) in the branded layout.

    A greeting line becomes the heading, a closing "Venlig hilsen …" is dropped (the layout adds its own), and the
    first stand-alone link or "Label: link" line becomes the button. `lang` is the language of the layout's own
    words; the greeting and closing of that language are recognised as well as the Danish ones."""
    lang = normalize(lang)
    greetings = tuple(dict.fromkeys(GREETING_WORDS["da"] + GREETING_WORDS.get(lang, ())))
    closings = tuple(dict.fromkeys(("venlig hilsen", t(lang, "regards").lower())))
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body.strip()) if b.strip()]
    heading = subject
    if blocks and re.match(r"^(" + "|".join(re.escape(g) for g in greetings) + r")\b", blocks[0]) and "\n" not in blocks[0]:
        heading = blocks.pop(0).rstrip(",")
    if blocks and blocks[-1].lower().startswith(closings):
        blocks.pop()
    button_label = button_url = None
    kept: list[str] = []
    for b in blocks:
        m = re.fullmatch(r"(?:(.{2,60}?):\s*)?(https?://\S+)", b)
        if button_url is None and m:
            button_label, button_url = (m.group(1) or t(lang, "open")).strip(), m.group(2)
            continue
        if button_url is None and "\n" in b:
            lines = b.split("\n")
            if _URL.fullmatch(lines[-1].strip()):
                button_url = lines[-1].strip()
                button_label = t(lang, "open")
                b = "\n".join(lines[:-1]).strip()
        kept.append(b)
    return Email(subject=subject, heading=heading, paragraphs=kept, button_label=button_label, button_url=button_url,
                 footer_reason=footer_reason or t(lang, "footer_account"), lang=lang)


# --------------------------------------------------------------------------- the emails
# Every builder takes `lang` (app/core/languages.py; Danish is the source). The texts live in email_texts.py.

def verify(link: str, lang: str = "da", *, privat: bool = False, variant: str = "trial") -> Email:
    """`privat`: the sign-up came from Dialogbot Privat – its own words (no «AI-receptionist»), F-PK-04. `variant`
    (privat_context.next_kind): "trial" may mention the trial; "list" (a shared list or group – a free account) and
    "other" promise no trial (F-JP-05)."""
    lang = normalize(lang)
    sfx = "_privat" if privat else ""
    body = {"list": "verify_body_privat_list", "other": "verify_body_privat_neutral"}.get(variant, "verify_body" + sfx) \
        if privat else "verify_body"
    return Email(
        subject=t(lang, "verify_subject"),
        preheader=t(lang, "verify_preheader"),
        heading=t(lang, "verify_heading" + sfx),
        step=1,
        paragraphs=[t(lang, body)],
        button_label=t(lang, "verify_button"), button_url=link,
        note=t(lang, "verify_note"),
        footer_reason=t(lang, "verify_footer"), lang=lang, audience="privat" if privat else "erhverv")


def reset(link: str, lang: str = "da", *, privat: bool = False) -> Email:
    """`privat`: a Privat-only account or a reset asked for from a Privat page – the Privat layout (F-JP-02)."""
    lang = normalize(lang)
    return Email(
        subject=t(lang, "reset_subject"),
        preheader=t(lang, "reset_preheader"),
        heading=t(lang, "reset_heading"),
        paragraphs=[t(lang, "reset_body")],
        button_label=t(lang, "reset_button"), button_url=link,
        note=t(lang, "reset_note"),
        footer_reason=t(lang, "footer_account"), lang=lang, audience="privat" if privat else "erhverv")


def invitation(workspace: str, invited_by: str, role: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    r = _role(role, lang)
    return Email(
        subject=t(lang, "invitation_subject", invited_by=invited_by, workspace=workspace),
        preheader=t(lang, "invitation_preheader", role=r),
        heading=t(lang, "invitation_heading", workspace=workspace),
        paragraphs=[t(lang, "invitation_body", invited_by=invited_by, workspace=workspace, role=r)],
        button_label=t(lang, "invitation_button"), button_url=link,
        note=t(lang, "invitation_note"),
        footer_reason=t(lang, "invitation_footer", invited_by=invited_by), lang=lang)


def new_lead(workspace: str, contact_name: str, need: str, link: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    name = contact_name or t(lang, "lead_someone")
    return Email(
        subject=t(lang, "lead_subject", name=name),
        preheader=need[:90] if need else t(lang, "lead_preheader", name=name),
        heading=t(lang, "lead_heading"),
        paragraphs=[t(lang, "lead_body", name=name, workspace=workspace),
                    t(lang, "lead_need", need=need or t(lang, "lead_need_missing"))],
        button_label=t(lang, "lead_button"), button_url=link,
        footer_reason=t(lang, "lead_footer", workspace=workspace), lang=lang)


def intro_mail(business: str) -> Email:
    """The one fixed mail a business gets after it said yes to «send en mail» in a Privat call (docs/sales/privat-opkald-leads.md).
    Fixed text on purpose: verified facts only, no prices, no comparisons; it says why they get it and how to stop it."""
    return Email(
        subject="Kort om Dialogbot – som du bad om i telefonen",
        preheader="En digital telefonassistent, der tager telefonen, når I ikke kan.",
        heading="Tak for en kort snak",
        paragraphs=[f"Hej {business}. I sagde ja til en mail, da vi ringede til jer på vegne af en kunde. Her er den.",
                    "Dialogbot er en digital telefonassistent til små virksomheder. Den tager telefonen, når I ikke kan, "
                    "svarer ud fra det, I selv har godkendt, og giver jer besked om det, den som ringede, ville have.",
                    "Vil I høre mere, så svar på denne mail, eller ring til os på 93 70 34 33. Vil I ikke høre fra os igen, så "
                    "svar »nej tak«. Så skriver vi ikke mere."],
        button_label="Se Dialogbot", button_url="https://www.dialogbot.dk",
        footer_reason="Du får denne e-mail, fordi I sagde ja til den i en telefonsamtale.")


# The label of the internal AI counter in every language: that line stays in the app, never in the mail.
_AI_LABELS = tuple({TEXTS[x]["report_ai_label"] for x in TEXTS})


def daily_report(subject: str, body: str, link: str | None, lang: str = "da") -> Email:
    """The day's numbers as a small panel, then who called. Internal counters (AI answers) stay in the app.

    `subject` and `body` come from app/modules/reports/service.py, already in `lang`."""
    lang = normalize(lang)
    lines = body.split("\n")
    heading = lines[0] if lines else subject
    blocks = [b.strip() for b in re.split(r"\n\s*\n", "\n".join(lines[1:]).strip()) if b.strip()]
    rows: list[tuple[str, str]] = []
    paragraphs: list[str] = []
    for b in blocks:
        facts = [ln.split(": ", 1) for ln in b.split("\n") if ": " in ln and not ln.startswith("- ")]
        if not rows and facts and len(facts) == len(b.split("\n")):
            rows = [(k, v) for k, v in facts if not k.startswith(_AI_LABELS)]
        else:
            paragraphs.append(b)
    return Email(subject=subject, heading=heading, paragraphs=paragraphs, rows=rows,
                 preheader=t(lang, "report_preheader"),
                 button_label=t(lang, "report_button") if link else None, button_url=link,
                 footer_reason=t(lang, "report_footer"), lang=lang)


# --------------------------------------------------------------------------- ambassador programme

def ambassador_parent(parent_name: str, ambassador_name: str, ambassador_email: str, link: str, rules: str,
                      bonus: str, share: str, months: int, lang: str = "da") -> Email:
    lang = normalize(lang)
    first = ambassador_name.split()[0]
    return Email(
        subject=t(lang, "amb_parent_subject", first=first),
        preheader=t(lang, "amb_parent_preheader", first=first),
        heading=t(lang, "greeting", name=parent_name),
        paragraphs=[t(lang, "amb_parent_p1", ambassador_name=ambassador_name, ambassador_email=ambassador_email),
                    t(lang, "amb_parent_p2", bonus=bonus, share=share, months=months, first=first),
                    t(lang, "amb_parent_p3", first=first),
                    t(lang, "amb_parent_p4", first=first, rules=rules)],
        button_label=t(lang, "amb_parent_button"), button_url=link,
        note=t(lang, "amb_parent_note"),
        footer_reason=t(lang, "amb_parent_footer", ambassador_name=ambassador_name), lang=lang)


def ambassador_approved(first_name: str, link: str, code: str, portal: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    return Email(
        subject=t(lang, "amb_approved_subject"),
        preheader=t(lang, "amb_approved_preheader", code=code),
        heading=t(lang, "amb_approved_heading", first_name=first_name),
        paragraphs=[t(lang, "amb_approved_p1"), t(lang, "amb_approved_code", link=link, code=code),
                    t(lang, "amb_approved_p3")],
        button_label=t(lang, "amb_approved_button"), button_url=portal,
        footer_reason=t(lang, "amb_footer_signed_up"), lang=lang)


def ambassador_rejected(first_name: str, note: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    paras = [t(lang, "amb_rejected_p1")]
    if note:
        paras.append(note)
    paras.append(t(lang, "amb_reply"))
    return Email(subject=t(lang, "amb_rejected_subject"), heading=t(lang, "greeting", name=first_name), paragraphs=paras,
                 footer_reason=t(lang, "amb_footer_signed_up"), lang=lang)


def ambassador_paid(first_name: str, amount: str, bank_last4: str | None, number: int, b_income: bool,
                    portal: str, lang: str = "da") -> Email:
    lang = normalize(lang)
    paras = [t(lang, "amb_paid_transfer", amount=amount,
               bank=t(lang, "amb_paid_bank", last4=bank_last4) if bank_last4 else ""),
             t(lang, "amb_paid_statement", number=number)]
    if b_income:
        paras.append(t(lang, "amb_paid_b_income"))
    paras.append(t(lang, "amb_paid_thanks"))
    return Email(subject=t(lang, "amb_paid_subject", amount=amount), preheader=t(lang, "amb_paid_preheader"),
                 heading=t(lang, "amb_paid_heading", first_name=first_name), paragraphs=paras,
                 button_label=t(lang, "amb_paid_button"), button_url=portal,
                 footer_reason=t(lang, "amb_paid_footer"), lang=lang)


def social_drafts_waiting(items: list[tuple[str, str]], link: str, skip_after_hours: int = 6, lang: str = "da") -> Email:
    """Operator reminder: drafts of Dialogbot's own social posts that are not approved shortly before their slot.
    `items` = (platform and time, topic) per draft. Nothing is posted without the approval. Dialogbot's operators
    work in Danish, so the caller leaves `lang` at Danish."""
    lang = normalize(lang)
    n = len(items)
    return Email(
        subject=t(lang, "social_subject_many", n=n) if n != 1 else t(lang, "social_subject_one"),
        preheader=t(lang, "social_preheader"),
        heading=t(lang, "social_heading"),
        paragraphs=[t(lang, "social_body")],
        rows=list(items),
        button_label=t(lang, "social_button"), button_url=link,
        note=t(lang, "social_note", hours=skip_after_hours),
        footer_reason=t(lang, "social_footer"), lang=lang)


def to_payload(mail: Email) -> dict:
    """Serialize for the outbox (the worker renders it with `from_payload`)."""
    return {"subject": mail.subject, "heading": mail.heading, "paragraphs": mail.paragraphs,
            "button_label": mail.button_label, "button_url": mail.button_url, "note": mail.note,
            "footer_reason": mail.footer_reason, "preheader": mail.preheader, "step": mail.step,
            "rows": [list(r) for r in mail.rows], "lang": mail.lang, "audience": mail.audience}


def from_payload(p: dict) -> Email:
    """A structured payload (`email` key) or an older free-text one (`subject` + `body`)."""
    if isinstance(p.get("email"), dict):
        data = {k: v for k, v in p["email"].items() if k in Email.__dataclass_fields__}
        data["rows"] = [(str(k), str(v)) for k, v in data.get("rows") or []]
        return Email(**data)
    lang = normalize(p.get("lang"))
    return from_plain(p.get("subject") or t(lang, "default_subject"), p.get("body") or "", lang=lang)


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
        "social_drafts_waiting": social_drafts_waiting(
            [("Facebook · i dag kl. 15.30", "Booking"), ("Instagram · i dag kl. 16.15", "Booking"),
             ("TikTok · i dag kl. 19.00", "Booking")], "https://www.dialogbot.dk/app/operator/social"),
        "intro_mail": intro_mail("Salon Test"),
        "from_plain": from_plain("Gammel besked", "Hej Mads\n\nTekst her.\n\nSe det her: https://www.dialogbot.dk/x\n\n"
                                                  "Venlig hilsen\nDialogbot"),
    }
