"""Hard limits as data: the patterns the code enforces. Danish + English.

Matching is on the START of a word (so «Bekræfter» and «payment» match, «Algemene» does not match «gem»). A false
positive only costs a human yes or a phone fallback; a false negative could commit something. When in doubt, widen.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# --- forbidden fields (type / name / autocomplete / label ...) -------------------------------------------------
FORBIDDEN_FIELD_RE = re.compile(
    r"(?<!\w)(?:password|passwd|pwd|kodeord|adgangskode|passphrase"
    r"|card|cc-|cvc|cvv|kreditkort|betalingskort|kort(?:nummer|nr)|kortnr|iban|bank\s*konto"
    r"|udløb|expir|exp[-_ ]?(?:month|year|date|mm|yy)"
    r"|cpr|personnummer|ssn|social[- ]security)",
    re.IGNORECASE,
)

# --- forbidden clicks (visible text / aria-label / value) ------------------------------------------------------
# The first nine are the brief's list; the rest are widenings for buttons that commit under another label.
COMMIT_WORDS = (
    "bekræft", "book nu", "gennemfør", "betal", "send", "confirm", "submit", "pay", "complete",
    "bestil", "reserver", "afslut", "godkend", "accept", "place order", "order now", "køb", "buy", "finish",
    "indsend", "tilmeld", "opret booking",
)
# «fortsæt» and «næste» are deliberately NOT here: they are normal wizard steps. A site that hides the real commit
# behind such a label is caught afterwards by `looks_like_receipt` (unexpected_commit), see session.click.
FORBIDDEN_CLICK_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in COMMIT_WORDS) + ")", re.IGNORECASE)

# --- CAPTCHA / login --------------------------------------------------------------------------------------------
CAPTCHA_HOSTS = (
    "google.com/recaptcha", "gstatic.com/recaptcha", "recaptcha.net", "hcaptcha.com", "challenges.cloudflare.com",
    "arkoselabs.com", "funcaptcha.com", "geetest.com", "friendlycaptcha.com", "captcha-delivery.com", "mtcaptcha.com",
    "perimeterx.net", "px-cdn.net",
)
CAPTCHA_SELECTORS = (".g-recaptcha", ".h-captcha", ".cf-turnstile", "[data-sitekey]", "#px-captcha", "[class*='captcha' i]")
LOGIN_TEXT_RE = re.compile(
    r"(?:log\s*ind|login|sign\s*in|opret\s+(?:en\s+)?konto|create\s+an?\s+account)\s+(?:for\s+at|to)\s+"
    r"|du\s+skal\s+(?:være\s+)?logget\s+ind|du\s+skal\s+logge\s+ind|you\s+(?:must|need\s+to)\s+(?:log|sign)\s*in"
    r"|please\s+(?:log|sign)\s*in",
    re.IGNORECASE,
)


def matches_forbidden_field(*parts: str | None) -> str | None:
    """The matching text if any of the attribute/label strings names a field we never fill, else None."""
    for p in parts:
        if p and (m := FORBIDDEN_FIELD_RE.search(p)):
            return m.group(0)
    return None


def matches_forbidden_click(*parts: str | None) -> str | None:
    for p in parts:
        if p and (m := FORBIDDEN_CLICK_RE.search(p)):
            return m.group(0)
    return None


def is_captcha_url(url: str) -> bool:
    low = (url or "").lower()
    if low.startswith("//"):
        low = "https:" + low
    try:
        parts = urlsplit(low)
        hostpath = f"{parts.hostname or ''}{parts.path}"
    except ValueError:
        hostpath = low
    return any(h in hostpath for h in CAPTCHA_HOSTS)


# --- safety net: did an unapproved click just commit something? -----------------------------------------------------
RECEIPT_RE = re.compile(
    r"tak\s+for\s+din\s+(?:booking|bestilling|reservation)|din\s+tid\s+er\s+(?:booket|bekræftet)|bekræftelse|kvittering"
    r"|booking\s+(?:is\s+)?confirmed|reservation\s+(?:is\s+)?complete|thank\s+you\s+for\s+(?:your\s+)?booking",
    re.IGNORECASE,
)


def looks_like_receipt(text: str, *, commit_buttons_left: bool) -> str | None:
    """The matching phrase if the page reads like a booking receipt AND no commit button is left on it.

    A summary page titled «Bekræftelse af oplysninger» still offers «Bekræft booking»: that is a page before the commit,
    not a receipt. A page that mentions «kvittering» but has no button to press is what a committed booking looks like.
    """
    if commit_buttons_left:
        return None
    m = RECEIPT_RE.search(text or "")
    return m.group(0) if m else None
