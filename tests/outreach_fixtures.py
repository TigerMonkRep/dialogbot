"""Shared set-up for the cold outreach tests (tests/test_outreach_*.py): dry-run mode, a recording stand-in for the
Anthropic client (no request ever leaves the process) and an MX lookup that answers yes."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.modules.outreach import llm
from app.modules.outreach.agents import dispatcher
from app.modules.outreach.agents.sourcing import RawLead
from app.modules.outreach.fake import FakeClaude
from app.modules.outreach.pipelines import batch as pipeline

PAIN = "Google review: Great work, but I called three times and it went to voicemail every time."


def raw(country: str = "US", email: str = "office@brightwater.example", company: str = "Brightwater Plumbing LLC",
        **kw) -> RawLead:
    base = dict(company_name=company, email=email, country=country, city="Austin", niche="plumber",
                website="https://brightwater.example", email_source="published_website",
                email_source_url="https://brightwater.example/contact", context=PAIN)
    return RawLead(**{**base, **kw})


@pytest.fixture
def outreach(monkeypatch):
    monkeypatch.setenv("OUTREACH_MODE", "dry_run")
    monkeypatch.setenv("OUTREACH_WEB_SEARCH", "false")
    get_settings.cache_clear()
    fake = FakeClaude()
    llm.set_client_override(fake)
    yield fake
    llm.set_client_override(None)
    dispatcher.set_provider_override(None)
    get_settings.cache_clear()


def run(db, raws, batch: str = "t1", **kw) -> dict:
    kw.setdefault("mx_check", lambda _d: True)
    kw.setdefault("cvr_lookup", lambda _c: False)
    return pipeline.run_batch(db, raws, batch=batch, **kw)


def env(monkeypatch, **values) -> None:
    for k, v in values.items():
        monkeypatch.setenv(k, str(v))
    get_settings.cache_clear()
