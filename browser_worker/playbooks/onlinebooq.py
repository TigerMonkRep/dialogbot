"""Playbook: OnlineBooq public booking flow (ydelse → medarbejder → dato → tid → kontaktoplysninger → bekræft).

!!! NOT VERIFIED AGAINST A REAL OnlineBooq PAGE !!!
This file was written from the public flow's shape and tested against tests/sites/onlinebooq/ (a clone). Every selector
below is a GUESS about the visible wording. They are text patterns (regexes on the accessible name), not CSS, and they
all live in SELECTORS so that a mismatch found on a real page is fixed HERE, in one block, without touching the logic.
A selector that does not match raises PlaybookMiss, and the run falls through to the LLM fallback / phone track.

To add engine no. 2 (e.g. Planway): copy this file, change ENGINE and SELECTORS, adapt the step order if needed, and
register it in playbooks/__init__.py. See browser_worker/README.md.
"""
from __future__ import annotations

import re

from ..session import BrowserSession
from .common import (
    NoAvailability,
    PlaybookMiss,
    PlaybookUnsupported,
    Prepared,
    date_pattern,
    in_window,
    parse_pairs,
    parse_time,
    service_matches,
)

ENGINE = "onlinebooq"
SUPPORTED_INTENTS = ("book",)  # v1: flyt/aflys are not automated; they go to the LLM fallback / phone track

# =====================================================================================================================
# SELECTORS – the ONE place to adjust when a real page words things differently. Regexes, case-insensitive, matched
# against the element's accessible name (the text read_page shows). Nothing below is verified against a real site.
# =====================================================================================================================
SELECTORS = {
    # elements that are navigation, not choices (never treated as a service/staff/date option)
    "ignore": r"^(forside|home|tilbage|back|kontakt|contact|log\s*ind|login|opret\s+konto|sprog|language)$",
    # «any employee» option on the staff step
    "staff_any": r"ingen\s+pr[æe]ference|valgfri|vilk[åa]rlig|enhver|no\s+preference|any(\s+employee|\s+staff)?",
    # contact form fields (textbox accessible names)
    "field_name": r"^(navn|fulde\s+navn|name|full\s+name)",
    "field_phone": r"(telefon|mobil|tlf|phone|mobile)",
    "field_mail": r"(e-?mail|mail)",
    # the button that leaves the contact step / any intermediate step
    "continue": r"^(forts[æe]t|n[æe]ste|videre|continue|next)\b",
    # the button that COMMITS the booking (clicked only after human approval)
    "confirm": r"(bekr[æe]ft|book\s+nu|gennemf[øo]r|confirm|complete\s+booking)",
    # labels on the summary page and on the receipt (label → regex), values are read from the text that follows
    "summary": {
        "service": r"ydelse|behandling|service",
        "staff": r"medarbejder|behandler|staff|employee",
        "date": r"dato|date",
        "time": r"tid|tidspunkt|time",
        "price": r"pris|price|total",
        "name": r"navn|name",
    },
    "reference": r"(?:bookingnummer|booking\s*(?:nr\.?|number)|reference|ref\.?)\s*:?\s*([A-Z0-9][A-Z0-9-]{3,})",
    "receipt": r"tak\s+for\s+din\s+booking|din\s+tid\s+er\s+booket|booking\s+(?:is\s+)?confirmed|kvittering",
}
MAX_LOOPS = 14
# =====================================================================================================================


def _rx(key: str) -> re.Pattern:
    return re.compile(SELECTORS[key], re.IGNORECASE)


def _options(s: BrowserSession) -> list[dict]:
    ign = _rx("ignore")
    return [e for e in s.elements if e["role"] in ("link", "button") and e.get("name") and not ign.search(e["name"].strip())]


def _step_kind(s: BrowserSession) -> str:
    """Which wizard step is on screen? Decided from what the page offers, so a site that skips a step still works."""
    els = s.elements
    if any(e["role"] == "button" and _rx("confirm").search(e["name"]) for e in els):
        return "summary"
    if any(e["role"] == "textbox" and _rx("field_name").search(e["name"]) for e in els):
        return "contact"
    names = [e["name"] for e in _options(s)]
    if sum(1 for n in names if parse_time(n)) >= 1:
        return "time"
    if any(re.search(r"\b(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december|"
                     r"january|february|march|may|june|july|october|december)\b|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", n, re.I)
           for n in names):
        return "date"
    if any(_rx("staff_any").search(n) for n in names):
        return "staff"
    return "service"


def prepare(s: BrowserSession, goal: dict, start_url: str) -> Prepared:
    """Navigate to «filled in, but not confirmed» and return the before→after the user is asked to approve."""
    intent = goal.get("intent")
    if intent not in SUPPORTED_INTENTS:
        raise PlaybookUnsupported(f"intent_{intent}")
    windows = [w for w in (goal.get("preferred_windows") or []) if w.get("date")]
    if not windows:
        raise PlaybookMiss("no_preferred_windows")
    contact = goal.get("contact") or {}
    wanted = goal.get("service") or ""
    found: dict = {"service": wanted, "dates_seen": [], "times_seen": {}}
    tried_windows: set[int] = set()
    current: int | None = None
    s.navigate(start_url)
    last_sig = None
    for _ in range(MAX_LOOPS):
        s.read_page()
        kind = _step_kind(s)
        sig = (kind, s.page.url, tuple(e["name"] for e in s.elements))
        if sig == last_sig:
            raise PlaybookMiss("stuck", found)
        last_sig = sig
        if kind == "summary":
            return Prepared(before_after=_before_after(s, goal), meta={"found": found})
        if kind == "service":
            opts = _options(s)
            hit = next((e for e in opts if service_matches(e["name"], wanted)), None)
            found["services"] = [e["name"] for e in opts][:20]
            if hit is None:
                raise PlaybookMiss("service_not_found", found)
            s.click(hit["ref"])
        elif kind == "staff":
            ref = s.find("link", SELECTORS["staff_any"]) or s.find("button", SELECTORS["staff_any"])
            s.click(ref)
        elif kind == "date":
            names = [e["name"] for e in _options(s)]
            found["dates_seen"] = names[:30]
            pick = None
            for i, w in enumerate(windows):
                if i in tried_windows:
                    continue
                rx = date_pattern(w["date"])
                ref = next((e["ref"] for e in _options(s) if rx.search(e["name"])), None)
                if ref:
                    pick = (i, ref)
                    break
                tried_windows.add(i)
            if pick is None:
                raise NoAvailability(found)
            current = pick[0]
            s.click(pick[1])
        elif kind == "time":
            times = [(parse_time(e["name"]), e) for e in _options(s) if parse_time(e["name"])]
            found["times_seen"][windows[current or 0]["date"]] = [e["name"] for _, e in times]
            ok = next((e for t, e in times if in_window(t, windows[current or 0])), None)
            if ok is None:
                tried_windows.add(current or 0)
                s.back()
                continue
            s.click(ok["ref"])
        elif kind == "contact":
            _fill_contact(s, contact)
            ref = s.find("button", SELECTORS["continue"]) or s.find("link", SELECTORS["continue"])
            if not ref:
                raise PlaybookMiss("no_continue_button", found)
            s.click(ref)
    raise PlaybookMiss("too_many_steps", found)


def _fill_contact(s: BrowserSession, contact: dict) -> None:
    fields = [("field_name", contact.get("name")), ("field_phone", contact.get("phone")), ("field_mail", contact.get("mail"))]
    for key, value in fields:
        ref = s.find("textbox", SELECTORS[key])
        if ref and value:
            s.type(ref, str(value))
        elif ref is None and key == "field_name":
            raise PlaybookMiss("name_field_not_found")


def _before_after(s: BrowserSession, goal: dict) -> dict:
    pairs = parse_pairs(s.page_text(), SELECTORS["summary"])
    if not pairs.get("date") and not pairs.get("time"):
        raise PlaybookMiss("summary_not_understood")
    return {"engine": ENGINE, "intent": goal["intent"], "page_url": s.page.url, **pairs}


def confirm(s: BrowserSession) -> dict:
    """Press the one confirming element on the summary page and read the receipt.

    Without an approved session this raises ApprovalRequired from the click guard (the session stays alive, so the
    caller can hold it until the human answers). `commit=True` makes the playbook's own knowledge ("this is the
    confirm button") count even when the label is innocent."""
    s.read_page()
    ref = s.find("button", SELECTORS["confirm"]) or s.find("link", SELECTORS["confirm"])
    if ref is None:
        raise PlaybookMiss("confirm_button_not_found")
    s.click(ref, commit=True)
    s.read_page()
    lines = s.page_text()
    text = " ".join(ln.split('"', 1)[1].rsplit('"', 1)[0] for ln in lines if '"' in ln)
    receipt = bool(_rx("receipt").search(text))
    ref_m = re.search(SELECTORS["reference"], text, re.IGNORECASE)
    return {"confirmed": receipt, "reference": ref_m.group(1) if ref_m else None, "receipt_text": text[:600],
            "summary": parse_pairs(lines, SELECTORS["summary"])}
