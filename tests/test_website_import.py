"""Suggest knowledge from the company's website: crawl limits, SSRF guard, AI extraction into
drafts (never approved, prices never guessed), idempotent re-runs and honest failures."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.models import AiUsage, KnowledgeVersion, SourceImport
from app.modules.ai import provider as ai_provider
from app.modules.ai.provider import FakeProvider
from app.modules.knowledge import importer

SITE = {
    "https://fjordgulv.dk/": """<html><head><title>Fjord Gulvservice</title><script>var x=1</script></head><body>
        <nav><a href="/ydelser">Ydelser</a><a href="/kontakt">Kontakt</a><a href="/billede.jpg">Billede</a>
        <a href="https://andetfirma.dk/ydelser">Partner</a></nav>
        <h1>Fjord Gulvservice</h1><p>Vi sliber og behandler trægulve i hele Storkøbenhavn siden 1998.</p>
        <footer>Fjord Gulvservice ApS · Havnevej 12 · 8000 Aarhus · CVR 12345674</footer></body></html>""",
    "https://fjordgulv.dk/ydelser": """<html><body><h1>Vores ydelser</h1>
        <h2>Gulvafslibning</h2><p>Afslibning af trægulve med støvsuger-anlæg. Fra 145 kr. pr. m² inkl. moms.</p>
        <h2>Lakering</h2><p>Tre lag slidstærk lak på nyslebne gulve.</p></body></html>""",
    "https://fjordgulv.dk/kontakt": """<html><body><h1>Kontakt</h1><p>Ring på 70 12 34 56 hverdage 8-16.</p></body></html>""",
}


def fake_fetch(url):
    key = url if url in SITE else url + "/" if url + "/" in SITE else None
    return (key, SITE[key]) if key else None


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    ai_provider.set_provider_override(FakeProvider(get_settings()))
    monkeypatch.setattr(importer, "fetch", fake_fetch)
    yield
    ai_provider.set_provider_override(None)
    get_settings.cache_clear()


def test_parse_and_crawl_stay_on_site():
    title, text, links = importer.parse(SITE["https://fjordgulv.dk/"])
    assert title == "Fjord Gulvservice" and "var x" not in text and "## Fjord Gulvservice" in text
    assert "Ydelser" not in text  # navigation is not content
    pages = importer.crawl("https://fjordgulv.dk/", fake_fetch)
    urls = [p["url"] for p in pages]
    assert urls[0] == "https://fjordgulv.dk/" and "https://fjordgulv.dk/ydelser" in urls
    assert not any("andetfirma" in u or u.endswith(".jpg") for u in urls)
    assert urls.index("https://fjordgulv.dk/ydelser") < urls.index("https://fjordgulv.dk/kontakt")


def test_url_validation_and_ssrf_guard(monkeypatch):
    assert importer.normalize_url("fjordgulv.dk") == "https://fjordgulv.dk"
    with pytest.raises(ValidationFailed):
        importer.normalize_url("ftp://fjordgulv.dk")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ENABLE_DEV_TOOLS", "false")
    get_settings.cache_clear()
    try:
        assert importer._allowed("http://127.0.0.1:8000/") is False
        assert importer._allowed("http://10.0.0.5/") is False
        assert importer._allowed("http://169.254.169.254/latest/meta-data") is False
        assert importer._allowed("http://localhost/") is False
    finally:
        get_settings.cache_clear()


def test_import_creates_drafts_only(api, two_workspaces, fake_ai, db):
    t = two_workspaces
    tok, ws = t["tok_a"], t["ws_a"]
    r = api.post(tok, f"/workspaces/{ws}/knowledge/import", {})
    assert r.status_code == 422 and r.json()["field_errors"][0]["field"] == "url"  # no website on file yet
    r = api.post(tok, f"/workspaces/{ws}/knowledge/import", {"url": "fjordgulv.dk/"})
    assert r.status_code == 202, r.text
    latest = api.get(tok, f"/workspaces/{ws}/knowledge/imports/latest").json()["import"]
    assert latest["status"] == "done", latest
    titles = {i["title"]: i["kind"] for i in latest["created_items"]}
    assert titles == {"Gulvafslibning": "service", "Lakering": "service", "Om virksomheden": "fact",
                      "Åbningstider": "opening_hours"}
    assert latest["profile_suggestion"] == {
        "description": "Vi sliber og behandler trægulve i hele Storkøbenhavn siden 1998.", "cvr": "12345674",
        "phone": "70 12 34 56", "address_line": "Havnevej 12", "postal_code": "8000", "city": "Aarhus"}
    versions = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.source_type == "extraction")).all()
    assert {v.status for v in versions} == {"draft"}
    slib = next(v for v in versions if v.title == "Gulvafslibning")
    assert slib.content["price_net_minor"] is None and slib.content["unit"] == "m2"
    assert "145 kr. pr. m² inkl. moms" in slib.content["description"] and slib.source_ref == "https://fjordgulv.dk/ydelser"
    # nothing reaches the assistant before approval
    assert api.get(tok, f"/workspaces/{ws}/assistant/knowledge").json()["items"] == []
    usage = db.scalars(select(AiUsage).where(AiUsage.purpose == "source_import")).all()
    assert len(usage) == 1 and usage[0].prompt_version == "website-extract-v1"
    # a second run skips what already exists; other workspaces see nothing
    api.post(tok, f"/workspaces/{ws}/knowledge/import", {"url": "https://fjordgulv.dk/"})
    again = api.get(tok, f"/workspaces/{ws}/knowledge/imports/latest").json()["import"]
    assert again["created_items"] == [] and again["skipped"] == 4
    assert api.get(t["tok_b"], f"/workspaces/{t['ws_b']}/knowledge/imports/latest").json()["import"] is None


def test_import_roles_failures_and_not_configured(api, two_workspaces, fake_ai, db, monkeypatch):
    t = two_workspaces
    reader = api.add_member(t["tok_a"], t["ws_a"], "reader@testmail.dk", "reader")
    assert api.post(reader, f"/workspaces/{t['ws_a']}/knowledge/import", {"url": "https://fjordgulv.dk/"}).status_code == 403
    api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/knowledge/import", {"url": "https://findes-ikke.dk/"})
    failed = api.get(t["tok_a"], f"/workspaces/{t['ws_a']}/knowledge/imports/latest").json()["import"]
    assert failed["status"] == "failed" and "kunne ikke hentes" in failed["error"]
    ai_provider.set_provider_override(None)
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    r = api.post(t["tok_a"], f"/workspaces/{t['ws_a']}/knowledge/import", {"url": "https://fjordgulv.dk/"})
    assert r.status_code == 501 and r.json()["code"] == "ai_not_configured"
    assert db.scalar(select(SourceImport).where(SourceImport.status == "running")) is None


def test_profile_suggestion_keeps_only_what_the_pages_say():
    pages = [{"url": "https://x.dk/", "title": "", "text": "Ring 70 12 34 56. CVR 12345674. Havnevej 12, 8000 Aarhus."}]
    invented = {"profile": {"cvr": "12345682", "phone": "+45 99 88 77 66", "postal_code": "9000", "city": "Aalborg",
                            "address_line": "Strandvejen 1", "description": "kort"}}
    assert importer.profile_suggestion(invented, pages) == {}
    assert importer.cvr_valid("12345674") and not importer.cvr_valid("12345675") and not importer.cvr_valid("02345674")
    ok = {"profile": {"cvr": "DK-12 34 56 74", "phone": "+45 70 12 34 56"}}
    assert importer.profile_suggestion(ok, pages) == {"cvr": "12345674", "phone": "+45 70 12 34 56"}
    hours = importer.opening_hours({"opening_hours": {"weekly": [
        {"days": ["mon", "fri", "xyz"], "open": "08:00", "close": "16:00"},
        {"days": ["sat"], "open": "18:00", "close": "10:00"}], "note": "null"}})
    assert hours == {"weekly": [{"days": ["mon", "fri"], "open": "08:00", "close": "16:00"}], "closed_note": ""}
    assert importer.opening_hours({"opening_hours": None}) is None
