"""Browser worker, data layer (A2): the browser_runs table and the remembered booking-engine profiles."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import BrowserRun, BusinessBookingProfile, PrivateTask
from app.modules.browser import profiles

SITE = '<html><body><script src="/static/onlinebooq-widget.js"></script><a href="/booking/ydelse.html">Book tid online</a></body></html>'


def _task(api, pv, email):
    tok = pv.account(email)
    pv.say(tok, "Lav en liste med kaffe")
    return pv.ws(tok)


def test_browser_run_defaults_and_status_constraint(api, pv, db):
    ws = _task(api, pv, "mette@testmail.dk")
    task = db.scalar(select(PrivateTask).where(PrivateTask.workspace_id == ws))
    run = BrowserRun(task_id=task.id, workspace_id=ws, engine="onlinebooq", allowed_domains=["salon.dk"],
                     goal={"intent": "book", "service": "Herreklip"})
    db.add(run)
    db.commit()
    db.refresh(run)
    assert (run.status, run.max_steps, run.max_seconds, run.cost_cents) == ("planned", 25, 180, 0)
    assert run.steps == [] and run.evidence_urls == [] and run.before_after is None
    for status in ("planned", "running", "awaiting_approval", "approved", "done", "failed", "fallback_phone"):
        run.status = status
        db.commit()
    run.status = "wat"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deleting_the_task_deletes_its_runs(api, pv, db):
    ws = _task(api, pv, "mette@testmail.dk")
    task = db.scalar(select(PrivateTask).where(PrivateTask.workspace_id == ws))
    db.add(BrowserRun(task_id=task.id, workspace_id=ws, goal={}))
    db.commit()
    db.delete(task)
    db.commit()
    assert db.scalar(select(BrowserRun)) is None


def test_profile_is_detected_once_and_remembered(db):
    calls = []

    def fetch(url):
        calls.append(url)
        return url, SITE

    now = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    p = profiles.get_or_detect(db, website="Salon-X.dk", phone="+4512345678", fetch=fetch, now=now)
    db.commit()
    assert (p.engine, p.website_host, p.phone_e164) == ("onlinebooq", "salon-x.dk", "+4512345678")
    assert p.confidence >= 0.9 and p.booking_url
    n = len(calls)
    again = profiles.get_or_detect(db, website="https://salon-x.dk/", cvr="12345678", fetch=fetch, now=now + timedelta(days=30))
    assert again.id == p.id and len(calls) == n  # remembered: no new lookup
    assert again.cvr == "12345678"  # a better key is added to the same row
    assert db.scalar(select(BusinessBookingProfile).where(BusinessBookingProfile.cvr == "12345678")).id == p.id
    profiles.get_or_detect(db, website="salon-x.dk", fetch=fetch, now=now + timedelta(days=91))
    assert len(calls) > n  # stale after 90 days: looked at again


def test_unknown_engine_is_rechecked_sooner_and_a_failing_site_does_not_raise(db):
    def down(url):
        raise OSError("down")

    now = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    p = profiles.get_or_detect(db, website="nede.dk", fetch=down, now=now)
    assert (p.engine, p.confidence, p.booking_url) == ("unknown", 0.0, None)
    seen = []

    def up(url):
        seen.append(url)
        return url, SITE

    profiles.get_or_detect(db, website="nede.dk", fetch=up, now=now + timedelta(days=3))
    assert not seen  # unknown is kept for 7 days ...
    p = profiles.get_or_detect(db, website="nede.dk", fetch=up, now=now + timedelta(days=8))
    assert seen and p.engine == "onlinebooq"  # ... then looked at again


@pytest.mark.parametrize("raw", ["", "   ", "localhost", "ftp://x.dk", "javascript:alert(1)"])
def test_bad_websites_are_refused(raw):
    with pytest.raises(ValueError):
        profiles.normalize_website(raw)


def test_default_fetch_refuses_internal_addresses():
    from app.core.safe_fetch import FetchBlocked

    for url in ("http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://localhost/"):
        with pytest.raises(FetchBlocked):
            profiles.default_fetch(url)


def test_unique_website_host(db):
    db.add(BusinessBookingProfile(website_host="a.dk", website="https://a.dk/"))
    db.commit()
    db.add(BusinessBookingProfile(website_host="a.dk", website="https://a.dk/x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert uuid.UUID(str(db.scalar(select(BusinessBookingProfile.id))))
