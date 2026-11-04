"""The Erhverv funnel's industries and the «ca. N opkald om ugen» estimate.

The six buttons on /start map to the sales script's playbooks (app/modules/sales/script.INDUSTRIES), which is what the
demo call and the Places search use. The missed-calls table is Dialogbot's own working assumption per industry – an
estimate the visitor is told the source of and may correct (answers.missed_per_week overrides it). It is not a
statistic from a study, and the API never presents it as one.
"""
from __future__ import annotations

from app.modules.sales import script

# funnel key → label on the button, sales-script playbook, the standard voice the receptionist gets, and the weekly
# number of calls such a business typically cannot answer when nobody is ever free for the phone.
INDUSTRIES: dict[str, dict] = {
    "haandvaerker": {"label": "Håndværker", "script": "haandvaerk", "voice": "peter", "base": 18,
                     "description": "Håndværksvirksomhed (VVS, el, tømrer, maler, murer, gulv, tag)."},
    "klinik": {"label": "Klinik", "script": "klinik", "voice": "camilla", "base": 25,
               "description": "Klinik (tandlæge, fysioterapeut, kiropraktor, psykolog, dyrlæge)."},
    "salon": {"label": "Salon", "script": "skoenhed", "voice": "camilla", "base": 15,
              "description": "Frisør- eller skønhedssalon (frisør, barber, kosmetolog, negle, massage)."},
    "vaerksted": {"label": "Værksted", "script": "auto", "voice": "peter", "base": 20,
                  "description": "Autoværksted (service, syn, dækskift, plade)."},
    "raadgiver": {"label": "Rådgiver", "script": "raadgivning", "voice": "peter", "base": 12,
                  "description": "Rådgivning og kontor (advokat, revisor, ejendomsmægler, forsikring, IT)."},
    "restaurant": {"label": "Restaurant", "script": "restaurant", "voice": "camilla", "base": 22,
                   "description": "Hotel, restaurant eller café (bordbestilling, selskaber, værelser)."},
}
# The sales-script keys are accepted too (the website's "Ring mig op nu" uses them), and mapped to a funnel key.
_BY_SCRIPT = {v["script"]: k for k, v in INDUSTRIES.items()}

# Share of the weekly base that one «hvornår tager I ikke telefonen?» chip stands for. never_free = the whole base.
MISSED_WEIGHTS = {"lunch": 0.25, "after16": 0.35, "driving": 0.30, "weekend": 0.20, "never_free": 1.0}
MISSED_CHOICES = tuple(MISSED_WEIGHTS)
SOURCE = "Dialogbots skøn for branchen – ret tallet, hvis det ikke passer"
DEFAULT_BASE = 15


def normalize_industry(raw: str | None) -> str | None:
    """A funnel key, a sales-script key, or None."""
    key = (raw or "").strip().lower()
    if key in INDUSTRIES:
        return key
    return _BY_SCRIPT.get(key)


def script_key(industry: str | None) -> str | None:
    return INDUSTRIES[industry]["script"] if industry in INDUSTRIES else None


def label(industry: str | None) -> str:
    return INDUSTRIES[industry]["label"] if industry in INDUSTRIES else "virksomhed"


def voice_for(industry: str | None) -> str:
    return INDUSTRIES[industry]["voice"] if industry in INDUSTRIES else "camilla"


def playbook_label(industry: str | None) -> str | None:
    return script.industry_label(script_key(industry))


def estimate(industry: str | None, missed: list[str] | None, override: int | None = None) -> dict:
    """{missed_per_week, source}. The visitor's own number wins; otherwise the base scaled by the chips chosen."""
    if override is not None:
        return {"missed_per_week": max(0, min(int(override), 999)), "source": "Dit eget tal"}
    base = INDUSTRIES[industry]["base"] if industry in INDUSTRIES else DEFAULT_BASE
    chips = [c for c in (missed or []) if c in MISSED_WEIGHTS]
    if not chips:
        return {"missed_per_week": 0, "source": SOURCE}
    share = min(1.0, sum(MISSED_WEIGHTS[c] for c in chips))
    return {"missed_per_week": max(1, round(base * share)), "source": SOURCE}
