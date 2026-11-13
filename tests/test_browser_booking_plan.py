"""F-PDEC-02 (decision Fürster 2026-11-11): a booking on a business's website (browser worker) in Privat.

1. With a plan (or the trial) it is included and counts as an ordinary task: nothing moves on the Opkaldssaldo, no price.
2. Without a plan it is not possible – exactly like «Ring for mig»: 409 needs_plan with the CTA «Kræver en plan» → /privat/konto.
3. Fair use: a hidden cap of 30 website bookings per calendar month (Europe/Copenhagen) per workspace – then a friendly
   429 «Du har brugt månedens hjemmesidebookinger – prøv igen næste måned». The cap is never shown as a price.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.errors import ApiError, Conflict
from app.models import BrowserRun, CreditLedger, PrivateTask
from app.modules.billing import markets, prices
from app.modules.browser import service
from app.modules.privat import ledger, rules
from tests import test_browser_assistant as _ba
from tests.test_browser_assistant import book, runs, texts

_on, world = _ba._on, _ba.world  # the same autouse switch and fake CVR/Places/website

ROOT = Path(__file__).resolve().parents[1]
LIMIT_TEXT = "Du har brugt månedens hjemmesidebookinger – prøv igen næste måned"
GOAL = {"intent": "book", "service": "herreklip", "contact": {"name": "Mette Hansen"}}


@pytest.fixture
def user(pv):
    tok = pv.account("mette@testmail.dk")
    pv.verify_phone(tok)
    return tok


def _browser_rows(db, ws):
    db.expire_all()
    return [e for e in db.scalars(select(CreditLedger).where(CreditLedger.workspace_id == ws))
            if (e.source_ref or "").startswith("browser:")]


def _task(db, ws) -> PrivateTask:
    t = PrivateTask(workspace_id=ws, kind="call", title="Book herreklip", status="in_progress", next_step="",
                    paid_by="call", created_at=rules.now(), updated_at=rules.now())
    db.add(t)
    db.flush()
    return t


def _start(db, task):
    return service.start_run(db, task, goal=GOAL, allowed_domains=["salon-test.dk"], engine="onlinebooq",
                             booking_url="https://salon-test.dk/b")


def _past_runs(db, ws, n: int, at: datetime) -> None:
    task = _task(db, ws)
    for _ in range(n):
        db.add(BrowserRun(task_id=task.id, workspace_id=ws, engine="onlinebooq", allowed_domains=["salon-test.dk"],
                          goal=GOAL, status="done", created_at=at))
    db.commit()


# --- 1. with a plan: included, an ordinary task, nothing on the Opkaldssaldo -------------------------------------------------

def test_with_a_plan_a_website_booking_moves_nothing_on_the_balance(api, db, pv, user, world):
    ws = pv.ws(user)
    before = ledger.balance(db, ws)
    book(pv, user)
    [run] = runs(db)
    task = db.get(PrivateTask, run.task_id)
    assert ledger.balance(db, ws) == before and ledger.reserved(db, ws) == 0 and _browser_rows(db, ws) == []
    assert task.paid_by == "plan" and "kr" not in task.usage_text.lower() and "saldo" not in task.usage_text.lower()
    assert service.cas(db, run.id, "planned", "running")
    service.finish_done(db, db.get(BrowserRun, run.id), {"summary": {}})
    db.commit()
    db.expire_all()
    task = db.get(PrivateTask, run.task_id)
    assert ledger.balance(db, ws) == before and _browser_rows(db, ws) == []
    assert task.paid_by == "plan" and "kr" not in (task.usage_text or "").lower()


@pytest.mark.parametrize("plan", ["basis", "plus", "familie"])
def test_with_a_plan_an_empty_balance_still_books_online(api, db, pv, user, world, plan):
    pv.set_plan(user, plan)
    ws = pv.ws(user)
    ledger.add(db, ws, kind="spend", amount=-ledger.balance(db, ws), source_ref="test:drain", text="drain")
    db.commit()
    out = book(pv, user)
    assert "booke online" in texts(out) and len(runs(db)) == 1                    # not pushed to the phone for want of kroner
    assert ledger.balance(db, ws) == 0 and _browser_rows(db, ws) == []


def test_a_finished_run_from_before_the_decision_gives_its_hold_back(api, db, pv, user, world):
    """A run started under F-PDEC-01 reserved 2,90 kr.; it ends free now – booked or not – and the hold comes back."""
    ws = pv.ws(user)
    task = _task(db, ws)
    run = BrowserRun(task_id=task.id, workspace_id=ws, engine="onlinebooq", allowed_domains=["salon-test.dk"], goal=GOAL,
                     status="running")
    db.add(run)
    db.flush()
    ledger.reserve(db, ws, f"browser:{run.id}", 290, task_id=task.id, text="Booking på hjemmeside – reserveret")
    db.commit()
    assert ledger.balance(db, ws) == 1000 - 290
    for _ in range(2):
        service.finish_done(db, db.get(BrowserRun, run.id), {"summary": {}})
        db.commit()
    assert ledger.balance(db, ws) == 1000 and ledger.reserved(db, ws) == 0


def test_no_booking_price_exists_anywhere():
    assert not hasattr(prices, "PRIVAT_BROWSER_BOOKING_MINOR") and not hasattr(service, "BROWSER_BOOKING_MINOR")
    assert not hasattr(service, "booking_price")
    exported = json.dumps(markets.export(), ensure_ascii=False).lower()
    for word in ("browser", "website", "hjemmeside"):
        assert word not in exported
    for doc in ("docs/pricing.md", "docs/privat-api.md", "docs/ADR-004-browser-worker.md", "docs/implementation-progress.md"):
        for line in (ROOT / doc).read_text().splitlines():
            low = line.lower()
            if any(w in low for w in ("hjemmeside", "browser-booking", "browser-worker", "bookingpris")):
                assert not re.search(r"\d+,\d\d kr|\bkr\.|reserver", low) or "med i alle planer" in low, (doc, line)
    assert "med i alle planer" in (ROOT / "docs/pricing.md").read_text().lower()


# --- 2. without a plan: 409 needs_plan with «Kræver en plan» → /privat/konto -------------------------------------------------

def test_without_a_plan_start_run_is_409_needs_plan_with_the_cta(api, db, pv, user, world):
    pv.expire_trial(user)
    ws = pv.ws(user)
    task = _task(db, ws)
    with pytest.raises(Conflict) as e:
        _start(db, task)
    assert (e.value.status_code, e.value.code) == (409, "needs_plan")
    assert e.value.extra["cta"] == {"label": "Kræver en plan", "href": "/privat/konto"}
    db.rollback()
    assert _browser_rows(db, ws) == []


def test_without_a_plan_the_chat_offers_no_booking_tool_like_ring_for_mig(api, db, pv, user):
    from app.modules.privat import chat

    pv.expire_trial(user)
    names = {t["name"] for t in chat.tools_for(db, pv.ws(user))[0]}
    assert "start_booking" not in names                                             # the same gate as «Ring for mig»


def test_a_plan_that_lapses_mid_turn_gets_the_cta_and_nothing_starts(api, db, pv, user, world):
    from tests.test_browser_assistant import ChatModel, business_id

    ws = pv.ws(user)
    before = ledger.balance(db, ws)

    def start(m):
        pv.expire_trial(user)                                                       # the tools were already offered
        return [("start_booking", {"business_id": business_id(m), "intent": "book", "service": "herreklip",
                                   "preferred_windows": [{"date": "2026-11-10", "from": "09:00", "to": "12:00"}]})]

    from app.modules.ai import provider as ai_provider

    ai_provider.set_provider_override(ChatModel(lambda m: [("find_business", {"name": "Salon Test", "city": "Aarhus"})], start))
    out = pv.say(user, "Book herreklip hos Salon Test i Aarhus")
    assert not runs(db) and ledger.balance(db, ws) == before and _browser_rows(db, ws) == []
    assert not any(m["kind"] == "call_proposal" for m in out["messages"])        # the balance never pays instead
    [m] = [m for m in out["messages"] if m["role"] == "assistant" and m["options"]]
    assert m["kind"] == "text" and "kræver en plan" in m["text"].lower()
    assert m["options"] == [{"id": "cta:needs_plan", "label": "Kræver en plan", "sub": "/privat/konto"}]
    r = api.post(user, f"/privat/messages/{m['id']}/options/cta:needs_plan")
    assert r.status_code == 404, r.text                                                 # a marker, never an answer


# --- 3. fair use: 30 per Copenhagen calendar month, a friendly 429 ---------------------------------------------------------

def test_the_cap_is_one_constant_30():
    assert prices.PRIVAT_BROWSER_BOOKINGS_PER_MONTH == 30 and rules.BROWSER_BOOKINGS_PER_MONTH == 30
    assert service.BOOKINGS_PER_MONTH is rules.BROWSER_BOOKINGS_PER_MONTH or service.BOOKINGS_PER_MONTH == 30


def test_the_31st_booking_this_month_is_a_friendly_429(api, db, pv, user, world):
    ws = pv.ws(user)
    _past_runs(db, ws, 29, rules.now() - timedelta(days=1))
    _start(db, _task(db, ws))                                                       # the 30th is fine
    db.commit()
    with pytest.raises(ApiError) as e:
        _start(db, _task(db, ws))
    assert (e.value.status_code, e.value.code, e.value.message) == (429, "browser_booking_limit", LIMIT_TEXT)
    assert "kr" not in e.value.message and not set(e.value.extra) & {"limit", "price", "needed_minor"}
    db.rollback()


def test_the_cap_counts_the_copenhagen_month_and_the_workspace(api, db, pv, user, world):
    ws = pv.ws(user)
    # 1 November 00:30 in Copenhagen is still 31 October in UTC: it counts for November
    _past_runs(db, ws, 1, datetime(2026, 10, 31, 23, 30, tzinfo=UTC))
    _past_runs(db, ws, 29, datetime(2026, 10, 31, 22, 30, tzinfo=UTC))             # 31 October 23:30 in Copenhagen: October
    other = pv.account("anna@testmail.dk")
    _past_runs(db, pv.ws(other), 30, rules.now())                                   # another workspace's month is its own
    _start(db, _task(db, ws))                                                       # 2nd this month
    db.commit()
    assert service.bookings_this_month(db, ws) == 2
    with pytest.raises(ApiError) as e:
        _start(db, _task(db, pv.ws(other)))
    assert e.value.status_code == 429
    db.rollback()


def test_at_the_cap_the_chat_says_so_and_starts_nothing(api, db, pv, user, world):
    ws = pv.ws(user)
    _past_runs(db, ws, 30, rules.now())
    out = book(pv, user)
    assert len(runs(db)) == 30 and LIMIT_TEXT in texts(out)
    assert not any(m["kind"] == "call_proposal" for m in out["messages"])
    [m] = [m for m in out["messages"] if LIMIT_TEXT in m["text"]]
    assert m["options"] == [{"id": "notice:browser_booking_limit", "label": "", "sub": ""}]


def test_the_limit_text_exists_in_all_8_languages_and_never_names_a_number_or_price():
    base = ROOT / "web/src/i18n/messages"
    # "us" is a market edition generated from "en", not a ninth language – it is checked too
    langs = sorted(p.name for p in base.iterdir() if p.is_dir())
    assert len([lang for lang in langs if lang != "us"]) == 8
    for lang in langs:
        b = json.loads((base / lang / "privat.json").read_text())["browser"]
        assert b["limit"] and "30" not in b["limit"] and "kr" not in b["limit"].lower(), lang
        assert b["needsPlanText"], lang
    da = json.loads((base / "da" / "privat.json").read_text())["browser"]
    assert da["limit"] == LIMIT_TEXT
