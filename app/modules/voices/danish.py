"""Danish text → speakable text for speech synthesis, and chunking into speech units.

Rules:
- Values never change: every number, amount, date, time, percentage, phone number and e-mail is
  spelled out so the *same value* is spoken (tests round-trip numbers through a parser).
- Times are read as digits ("klokken ti tredive"), not reworded to "halv elleve": a rewording could
  be misheard as a different time. Text already written as "halv elleve" is left alone.
- Phone numbers are read in groups of two digits ("tyve tredive fyrre halvtreds").
- Negations and words are never removed or reordered.
- The customer's pronunciation dictionary is applied first (whole words, case-insensitive).
- Chunking splits only between sentences (or at commas in very long sentences), after
  normalisation, so a number or date can never be split in two.
"""
from __future__ import annotations

import re

ONES = ["nul", "en", "to", "tre", "fire", "fem", "seks", "syv", "otte", "ni", "ti", "elleve", "tolv", "tretten",
        "fjorten", "femten", "seksten", "sytten", "atten", "nitten"]
TENS = {20: "tyve", 30: "tredive", 40: "fyrre", 50: "halvtreds", 60: "tres", 70: "halvfjerds", 80: "firs", 90: "halvfems"}
ORD_ONES = ["nulte", "første", "anden", "tredje", "fjerde", "femte", "sjette", "syvende", "ottende", "niende", "tiende",
            "ellevte", "tolvte", "trettende", "fjortende", "femtende", "sekstende", "syttende", "attende", "nittende"]
ORD_TENS = {20: "tyvende", 30: "tredivte"}
MONTHS = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober", "november",
          "december"]
ABBREVIATIONS = [
    (r"\bf\.eks\.", "for eksempel"), (r"\bfx\.?(?=\s)", "for eksempel"), (r"\bbl\.a\.", "blandt andet"),
    (r"\bca\.", "cirka"), (r"\binkl\.", "inklusive"), (r"\bekskl\.", "eksklusive"), (r"\bosv\.", "og så videre"),
    (r"\bevt\.", "eventuelt"), (r"\bnr\.", "nummer"), (r"\bpga\.", "på grund af"), (r"\bmht\.", "med hensyn til"),
    (r"\bdvs\.", "det vil sige"), (r"\bmin\.(?=\s)", "minutter"), (r"\bstk\.", "styk"),
]
LETTERS = {"a": "a", "b": "b", "c": "c", "d": "d", "e": "e", "f": "f", "g": "g", "h": "h", "i": "i", "j": "j",
           "k": "k", "l": "l", "m": "m", "n": "n", "o": "o", "p": "p", "q": "q", "r": "r", "s": "s", "t": "t",
           "u": "u", "v": "v", "w": "w", "x": "x", "y": "y", "z": "z", "æ": "æ", "ø": "ø", "å": "å"}


def _below_100(n: int, neuter: bool = False) -> str:
    if n < 20:
        return "et" if (n == 1 and neuter) else ONES[n]
    tens, ones = n // 10 * 10, n % 10
    return TENS[tens] if ones == 0 else f"{ONES[ones]}og{TENS[tens]}"


def _below_1000(n: int, neuter: bool = False) -> str:
    h, rest = divmod(n, 100)
    if h == 0:
        return _below_100(rest, neuter)
    head = "et hundrede" if h == 1 else f"{ONES[h]} hundrede"
    return head if rest == 0 else f"{head} og {_below_100(rest, neuter)}"


def number(n: int, neuter: bool = False) -> str:
    """Cardinal number in Danish words. 1495 → "et tusind fire hundrede og femoghalvfems"."""
    if n < 0:
        return "minus " + number(-n, neuter)
    if n >= 10**12:
        return " ".join(ONES[int(d)] for d in str(n))  # absurdly large: read digit by digit
    parts = []
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    if millions:
        parts.append("en million" if millions == 1 else f"{_below_1000(millions)} millioner")
    if thousands:
        parts.append("et tusind" if thousands == 1 else f"{_below_1000(thousands, True)} tusind")
    if units or not parts:
        words = _below_1000(units, neuter)
        if parts and units < 100:
            words = f"og {words}"  # "et tusind og fem"
        parts.append(words)
    return " ".join(parts)


def ordinal(n: int) -> str:
    """1–31 as Danish ordinals (dates)."""
    if n < 20:
        return ORD_ONES[n]
    if n in ORD_TENS:
        return ORD_TENS[n]
    tens, ones = n // 10 * 10, n % 10
    return f"{ONES[ones]}og{ORD_TENS[tens]}"


def year(y: int) -> str:
    return number(y, neuter=True)


def digit_pairs(digits: str) -> str:
    """Read digits in groups of two: "20304050" → "tyve tredive fyrre halvtreds"; "07" → "nul syv"."""
    out = []
    for i in range(0, len(digits), 2):
        pair = digits[i:i + 2]
        if len(pair) == 1:
            out.append(ONES[int(pair)])
        elif pair[0] == "0":
            out.append(f"nul {ONES[int(pair[1])]}")
        else:
            out.append(_below_100(int(pair)))
    return " ".join(out)


def _int(s: str) -> int:
    return int(s.replace(".", "").replace(" ", ""))


def _amount(whole: str, frac: str | None, unit: str) -> str:
    w = _int(whole)
    main = f"{number(w)} {'krone' if w == 1 else 'kroner'}" if unit == "kr" else f"{number(w)} {unit}"
    if frac and int(frac):
        f = int(frac.ljust(2, "0")[:2])
        main += f" og {number(f)} øre" if unit == "kr" else f" komma {digit_pairs(frac)}"
    return main


def _email(m: re.Match) -> str:
    local, domain = m.group(1), m.group(2)

    def spell(part: str) -> str:
        words = []
        for token in re.split(r"([._-])", part):
            if token == ".":
                words.append("punktum")
            elif token == "-":
                words.append("bindestreg")
            elif token == "_":
                words.append("understreg")
            elif token:
                words.append(" ".join(LETTERS.get(c, c) for c in token) if len(token) <= 3 else token)
        return " ".join(words)

    return f"{spell(local)} snabel-a {spell(domain)}"


def _phone(m: re.Match) -> str:
    raw = m.group(0)
    digits = re.sub(r"\D", "", raw)
    prefix = ""
    if raw.strip().startswith("+"):
        cc, digits = digits[:2], digits[2:]
        prefix = f"plus {_below_100(int(cc))}, "
    return prefix + digit_pairs(digits)


def _date(day: str, month: int, yr: str | None) -> str:
    d = int(day)
    out = f"den {ordinal(d)} {MONTHS[month - 1]}"
    if yr:
        out += f" {year(int(yr))}"
    return out


def _time(h: str, m: str) -> str:
    hh, mm = int(h), int(m)
    return f"klokken {number(hh)}" if mm == 0 else f"klokken {number(hh)} {_minutes(mm)}"


def _minutes(mm: int) -> str:
    return f"nul {ONES[mm]}" if mm < 10 else _below_100(mm)


def apply_pronunciations(text: str, entries: list[dict] | None) -> str:
    for e in sorted(entries or [], key=lambda x: -len(str(x.get("term", "")))):
        term, say = str(e.get("term", "")).strip(), str(e.get("say", "")).strip()
        if term and say:
            text = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", say, text, flags=re.IGNORECASE)
    return text


MONTH_RE = "|".join(MONTHS)


def normalize(text: str, pronunciations: list[dict] | None = None) -> str:
    """Speakable Danish. Pure function; the same input always gives the same output."""
    t = apply_pronunciations(text or "", pronunciations)
    t = re.sub(r"[ \t]+", " ", t.replace(" ", " ")).strip()
    # e-mail addresses before anything touches their dots
    t = re.sub(r"\b([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)\b", _email, t)
    # phone numbers: +45 20 30 40 50, 20 30 40 50, 20304050 (8 digits, not an amount)
    end = r"(?!\w|[.,]\d)"
    t = re.sub(rf"(?<![\w.,])\+\d{{2}}(?:[ -]?\d{{2}}){{4}}{end}", _phone, t)
    t = re.sub(rf"(?<![\w.,])\d{{2}}(?:[ -]\d{{2}}){{3}}{end}(?!\s*(?:kr\b|kroner|%|procent))", _phone, t)
    t = re.sub(rf"(?<![\w.,+])\d{{8}}{end}(?!\s*(?:kr\b|kroner|%|procent))", _phone, t)
    # dates: 28.10.2026, 28/10-2026, 28/10, "28. oktober [2026]"
    t = re.sub(r"\b(\d{1,2})[./](\d{1,2})[./-](\d{4})\b",
               lambda m: _date(m.group(1), int(m.group(2)), m.group(3)) if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31 else m.group(0), t)
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})\b",
               lambda m: _date(m.group(1), int(m.group(2)), None) if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31 else m.group(0), t)
    t = re.sub(rf"\b(?:den )?(\d{{1,2}})\. ({MONTH_RE})(?: (\d{{4}}))?\b",
               lambda m: _date(m.group(1), MONTHS.index(m.group(2).lower()) + 1, m.group(3)) if 1 <= int(m.group(1)) <= 31 else m.group(0),
               t, flags=re.IGNORECASE)
    # times: kl. 10.30, klokken 9:00, 14:15 (case of "Kl." at sentence start is kept)
    def cap(m: re.Match, out: str) -> str:
        return out[0].upper() + out[1:] if m.group(0)[0].isupper() else out

    t = re.sub(r"\b(?:kl\.|klokken) (\d{1,2})[.:](\d{2}) ?[-–] ?(\d{1,2})[.:](\d{2})\b",
               lambda m: cap(m, f"{_time(m.group(1), m.group(2))} til {_time(m.group(3), m.group(4))[8:]}"), t,
               flags=re.IGNORECASE)
    t = re.sub(r"\b(?:kl\.|klokken) (\d{1,2})[.:](\d{2})\b", lambda m: cap(m, _time(m.group(1), m.group(2))), t,
               flags=re.IGNORECASE)
    t = re.sub(r"\b(?:kl\.|klokken) (\d{1,2})\b(?![.:]\d)", lambda m: cap(m, f"klokken {number(int(m.group(1)))}"), t,
               flags=re.IGNORECASE)
    t = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lambda m: _time(m.group(1), m.group(2)), t)
    # amounts: 1.495 kr., 149,50 kroner, kr. 300
    num = r"(\d{1,3}(?:[. ]\d{3})+|\d+)(?:,(\d{1,2}))?"
    t = re.sub(rf"\b{num} ?(?:kr(\.)?|kroner|DKK)(?!\w)(?=(\s+[A-ZÆØÅ]|\s*$)?)",
               lambda m: _amount(m.group(1), m.group(2), "kr") + ("." if m.group(3) and m.group(4) is not None else ""), t)
    t = re.sub(rf"\b(?:kr\.?|DKK) ?{num}\b", lambda m: _amount(m.group(1), m.group(2), "kr"), t)
    # percent and units
    t = re.sub(rf"\b{num} ?%", lambda m: _amount(m.group(1), m.group(2), "procent"), t)
    t = re.sub(r"\b(\d+) ?(?:m²|m2|kvm)(?!\w)", lambda m: f"{number(int(m.group(1)))} kvadratmeter", t)
    # abbreviations (after times, so "kl." is handled above)
    for pat, rep in ABBREVIATIONS:
        t = re.sub(pat, lambda m, rep=rep: rep[0].upper() + rep[1:] if m.group(0)[0].isupper() else rep, t,
                   flags=re.IGNORECASE)
    t = re.sub(r"\bkl\.", "klokken", t)
    t = re.sub(r"\bKl\.", "Klokken", t)
    # decimals and remaining integers (with Danish thousands separators)
    t = re.sub(r"\b(\d+),(\d+)\b", lambda m: f"{number(int(m.group(1)))} komma {digit_pairs(m.group(2))}", t)
    t = re.sub(r"\b\d{1,3}(?:[. ]\d{3})+\b|\b\d+\b", lambda m: number(_int(m.group(0))), t)
    t = t.replace("&", " og ").replace("@", " snabel-a ")
    return re.sub(r"\s+", " ", t).strip()


def chunks(text: str, max_chars: int = 220) -> list[str]:
    """Split speakable text into speech units (sentences; long sentences at commas)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÆØÅ0-9\"'])", text)
    out: list[str] = []
    for s in sentences:
        if len(s) <= max_chars:
            out.append(s)
            continue
        buf = ""
        for part in re.split(r"(?<=,)\s+", s):
            if buf and len(buf) + len(part) + 1 > max_chars:
                out.append(buf)
                buf = part
            else:
                buf = f"{buf} {part}".strip()
        if buf:
            out.append(buf)
    return out
