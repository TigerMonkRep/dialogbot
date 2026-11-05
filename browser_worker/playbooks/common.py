"""Shared pieces for the deterministic playbooks (one module per booking engine)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class PlaybookMiss(Exception):
    """A selector/step did not work (or the intent is not supported): the LLM fallback may take over.

    `found` carries what was seen on the way (services, dates ...) so the phone track starts smarter if nothing else works.
    """

    def __init__(self, reason: str, found: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.found = found or {}


class PlaybookUnsupported(PlaybookMiss):
    """The engine's playbook does not do this intent (v1: only «book»)."""


class NoAvailability(Exception):
    """The site works, but nothing matches the user's windows. Not a selector problem: the LLM cannot invent a time.
    The run falls back to the phone track with `found` (service, dates and times seen)."""

    def __init__(self, found: dict):
        super().__init__("no_availability")
        self.found = found


@dataclass
class Prepared:
    """«Filled in, not confirmed»: what the user is asked to approve."""

    before_after: dict
    meta: dict = field(default_factory=dict)


MONTHS_DA = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november",
             "december"]
MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
             "december"]
TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\b")


def date_pattern(iso: str) -> re.Pattern:
    """Regex matching how a booking page may print the ISO date `2026-11-10`: «10. november», «10 Nov 2026», «10-11-2026» ..."""
    y, m, d = (int(x) for x in iso.split("-"))
    names = {MONTHS_DA[m - 1], MONTHS_EN[m - 1], MONTHS_DA[m - 1][:3], MONTHS_EN[m - 1][:3]}
    alt = "|".join(sorted(names, key=len, reverse=True))
    textual = rf"(?<!\d)0?{d}\.?\s*(?:{alt})\b"
    numeric = rf"(?<!\d)0?{d}[-/.]0?{m}[-/.](?:{y}|{y % 100:02d})(?!\d)"
    return re.compile(f"{textual}|{numeric}|{iso}", re.IGNORECASE)


def parse_time(name: str) -> tuple[int, int] | None:
    m = TIME_RE.match(name or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return (h, mi) if h < 24 and mi < 60 else None


def in_window(t: tuple[int, int], window: dict) -> bool:
    lo = parse_time(window.get("from") or "00:00") or (0, 0)
    hi = parse_time(window.get("to") or "23:59") or (23, 59)
    return lo <= t <= hi


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^\wæøå]+", (text or "").lower()) if len(t) >= 3]


def service_matches(option_name: str, wanted: str) -> bool:
    """Every word (≥ 3 letters) of the wanted service appears in the option's name."""
    name = (option_name or "").lower()
    ws = tokens(wanted)
    return bool(ws) and all(w in name for w in ws)


def text_values(lines: list[str]) -> list[str]:
    out = []
    for ln in lines:
        m = re.match(r'(?:text|heading\d) "(.*)"$', ln)
        if m:
            out.append(m.group(1))
    return out


def parse_pairs(lines: list[str], labels: dict[str, str]) -> dict[str, str]:
    """Pick label→value pairs from the page's text lines: «Ydelse» followed by «Herreklip», or «Ydelse: Herreklip»."""
    vals = text_values(lines)
    out: dict[str, str] = {}
    for key, pattern in labels.items():
        # (?!\w): the label must be a whole word («tid» must not read «Tidligere bookinger» or «Ventetid»)
        rx = re.compile(rf"^(?:{pattern})(?!\w)\s*:?\s*(.*)$", re.IGNORECASE)
        for i, v in enumerate(vals):
            m = rx.match(v.strip())
            if not m:
                continue
            if m.group(1):
                out[key] = m.group(1).strip()
            elif i + 1 < len(vals):
                out[key] = vals[i + 1].strip()
            break
    return out
