"""Social autoposting: copy per platform, brand images, planning, publishing, retries, the operator API and the
live platform calls (against a mocked transport – no network, no real accounts)."""
from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.core import crypto
from app.core.errors import ValidationFailed
from app.models import SocialCredential, SocialMedia, SocialPost
from app.modules.social import content, publishers, render, service
from app.modules.social.publishers import PublishError
from app.modules.social.topics import ALLOWED_AMOUNTS, FACTS, PLATFORMS, TOPICS, TOPICS_BY_KEY

CPH = ZoneInfo("Europe/Copenhagen")
MONDAY = datetime(2026, 10, 5, 6, 0, tzinfo=CPH)  # before every slot of the day


@pytest.fixture
def social(monkeypatch):
    """SOCIAL_PROVIDER=fake with all three platforms on and approval off."""
    monkeypatch.setenv("SOCIAL_PROVIDER", "fake")
    monkeypatch.setenv("SOCIAL_REQUIRE_APPROVAL", "false")
    monkeypatch.setenv("SOCIAL_PLATFORMS", "facebook,instagram,tiktok")
    monkeypatch.setenv("SOCIAL_WEEKDAYS", "0,2,4")
    monkeypatch.setenv("SOCIAL_PLAN_DAYS_AHEAD", "3")
    monkeypatch.setenv("SOCIAL_MAX_LATE_MINUTES", "1440")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.dialogbot.test")
    get_settings.cache_clear()
    publishers.FAKE_PUBLISHED.clear()
    publishers.FAKE_FAIL.clear()
    yield
    publishers.FAKE_PUBLISHED.clear()
    publishers.FAKE_FAIL.clear()
    get_settings.cache_clear()


# --- facts and copy ---------------------------------------------------------------------------------------------------

def test_prices_in_the_facts_match_the_website():
    assert any("1.495 kr." in f and "149 kr." in f for f in FACTS)
    assert ALLOWED_AMOUNTS == {"1.495", "149"}


@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.key)
@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_hand_written_post_passes_its_own_checks(topic, platform):
    d = content.template_draft(platform, topic)
    assert content.check(d) == []
    lo, hi = content.SLIDES[platform]
    assert lo <= len(d.slides) <= hi
    assert len(d.caption) <= {"facebook": 2000, "instagram": 2200, "tiktok": 4000}[platform]
    assert len(d.hashtags) <= content.TAG_LIMIT[platform]


def test_platforms_get_different_copy_links_and_hashtags():
    t = TOPICS_BY_KEY["pricing"]
    fb, ig, tt = (content.template_draft(p, t) for p in PLATFORMS)
    assert len({fb.caption, ig.caption, tt.caption}) == 3
    assert len({fb.slides[0]["title"], ig.slides[0]["title"], tt.slides[0]["title"]}) == 3
    assert (len(fb.slides), len(ig.slides), len(tt.slides)) == (1, 5, 5)
    assert "https://www.dialogbot.dk/priser" in fb.caption          # Facebook: clickable link
    assert "http" not in ig.caption and "Link i bio" in ig.caption   # Instagram: not clickable → bio
    assert "http" not in tt.caption and len(tt.caption) < 280
    assert len(ig.hashtags) > len(fb.hashtags) and all(f"#{h}" in ig.caption for h in ig.hashtags)


def _ai_draft(platform="instagram", **over):
    t = TOPICS_BY_KEY["pricing"]
    n = {"facebook": 1, "instagram": 5, "tiktok": 5}[platform]
    raw = {"slides": [{"title": f"Overskrift {i}", "body": "Kort tekst"} for i in range(n)],
           "caption": "Dialogbot tager telefonen døgnet rundt.", "hashtags": ["Dialogbot", "Telefon Pasning"]} | over
    return content.draft_from_ai(platform, t, raw, "test-model")


@pytest.mark.parametrize("over,needle", [
    ({"caption": "Kun 999 kr. om måneden"}, "amount not in the facts"),
    ({"caption": "Spar 30 % på telefonen"}, "forbidden phrase"),
    ({"caption": "Se https://example.com"}, "link"),
    ({"caption": "Brug #dialogbot i teksten"}, "hashtag"),
    ({"caption": "Vi er markedets bedste"}, "forbidden phrase"),
    ({"caption": "Prøv gratis i dag"}, "gratis"),
    ({"caption": ""}, "caption"),
    ({"caption": "x" * 3000}, "caption"),
])
def test_guard_rejects_what_the_facts_do_not_support(over, needle):
    d = _ai_draft(**over)
    assert any(needle in e for e in d.errors), d.errors


def test_guard_accepts_the_real_prices_and_clean_ai_copy():
    d = _ai_draft(caption="Fast abonnement er 1.495 kr. om måneden – eller 149 kr. pr. godkendt henvendelse.")
    assert d.errors == [] and d.generator == "ai" and d.model == "test-model"
    assert d.hashtags[0] == "dialogbot" and "telefonpasning" in d.hashtags      # cleaned, de-duplicated, topic tags added
    assert d.slides[0]["role"] == "hook" and d.slides[-1]["role"] == "cta" and d.slides[-1]["body"] == "dialogbot.dk"


def test_ai_slide_count_is_enforced_per_platform():
    with pytest.raises(ValueError):
        _ai_draft("instagram", slides=[{"title": "kun én"}])
    with pytest.raises(ValueError):
        _ai_draft("facebook", slides=[{"title": "a"}, {"title": "b"}])


def _completion(text, stop="end_turn"):
    return SimpleNamespace(text=text, stop_reason=stop, served_model="m")


def _ai_json(platform, good=True):
    n = {"facebook": 1, "instagram": 5, "tiktok": 5}[platform]
    return {"slides": [{"title": f"{platform} {i}", "body": ""} for i in range(n)],
            "caption": "Garanteret bedst." if not good else f"Tekst til {platform}.", "hashtags": ["x"]}


def test_ai_copy_is_used_per_platform_and_bad_platforms_fall_back(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    data = {"facebook": _ai_json("facebook"), "instagram": _ai_json("instagram", good=False), "tiktok": _ai_json("tiktok")}
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _completion(f"```json\n{json.dumps(data)}\n```"))
    drafts = {d.platform: d for d in content.generate(db, TOPICS_BY_KEY["pricing"])}
    assert drafts["facebook"].generator == "ai" and drafts["tiktok"].generator == "ai"
    assert drafts["instagram"].generator == "template"          # failed the guard ("garanteret", "bedst")
    get_settings.cache_clear()


@pytest.mark.parametrize("answer", [_completion("ikke json"), _completion("", "refusal"), _completion("{}", "max_tokens")])
def test_unusable_ai_answers_fall_back_to_hand_written_copy(monkeypatch, db, answer):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    monkeypatch.setattr(content, "_complete", lambda db, system, user: answer)
    assert {d.generator for d in content.generate(db, TOPICS_BY_KEY["booking"])} == {"template"}
    get_settings.cache_clear()


def test_ai_off_means_hand_written_copy_without_a_call(monkeypatch, db):
    monkeypatch.setattr(content, "_complete", lambda *a: pytest.fail("the AI must not be called"))
    assert {d.generator for d in content.generate(db, TOPICS_BY_KEY["booking"])} == {"template"}


def test_the_ai_prompt_contains_only_the_verified_facts(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    seen = {}

    def fake(db, system, user):
        seen["system"], seen["user"] = system, user
        return _completion("nej")

    monkeypatch.setattr(content, "_complete", fake)
    content.generate(db, TOPICS_BY_KEY["pricing"], recent_hooks=["Gammel hook"])
    assert all(f in seen["system"] for f in FACTS) and "Gammel hook" in seen["user"]
    get_settings.cache_clear()


# --- images ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("platform,size,count", [("facebook", (1080, 1080), 1), ("instagram", (1080, 1350), 5),
                                                 ("tiktok", (1080, 1920), 5)])
def test_images_are_jpeg_in_each_platforms_format(platform, size, count):
    d = content.template_draft(platform, TOPICS_BY_KEY["industry_haandvaerkere"])
    imgs = render.render_post(platform, d.slides)
    assert len(imgs) == count
    for data, w, h in imgs:
        assert data[:3] == b"\xff\xd8\xff" and (w, h) == size            # JPEG: the only format Instagram accepts
        im = Image.open(io.BytesIO(data))
        assert im.size == size and len(data) < 400_000


def test_text_the_font_cannot_draw_is_dropped_and_long_text_still_fits():
    assert render.printable("Hej ✔ 👋 → æøå – ok") == "Hej æøå – ok"
    long = {"role": "point", "kicker": "1 / 3", "title": "Meget lang overskrift " * 12, "body": "Brødtekst " * 40}
    assert render.render_slide("tiktok", long, 1, 5)[:3] == b"\xff\xd8\xff"


# --- planning ----------------------------------------------------------------------------------------------------------

def test_plan_creates_one_topic_per_day_in_three_different_posts(social, db):
    created = service.plan(db, MONDAY)
    assert len(created) == 6                                            # Monday + Wednesday × 3 platforms
    by_day = {}
    for p in created:
        by_day.setdefault(p.slot_date, []).append(p)
    assert sorted(by_day) == [date(2026, 10, 5), date(2026, 10, 7)]
    for posts in by_day.values():
        assert {p.platform for p in posts} == set(PLATFORMS) and len({p.topic for p in posts}) == 1
        assert len({p.caption for p in posts}) == 3 and all(p.status == "scheduled" for p in posts)
    assert len({posts[0].topic for posts in by_day.values()}) == 2      # a new topic each day
    slots = {p.platform: p.scheduled_for.astimezone(CPH).strftime("%H:%M") for p in by_day[date(2026, 10, 5)]}
    assert slots == {"facebook": "09:30", "instagram": "12:15", "tiktok": "19:00"}
    media = db.scalars(select(SocialMedia)).all()
    assert len(media) == 2 * (1 + 5 + 5) and all(m.data[:2] == b"\xff\xd8" for m in media)


def test_planning_twice_does_not_duplicate_and_skips_slots_that_have_passed(social, db):
    assert len(service.plan(db, MONDAY.replace(hour=10))) == 5          # Monday's Facebook slot (09:30) is gone
    assert service.plan(db, MONDAY.replace(hour=10)) == []
    assert db.scalars(select(SocialPost.platform).where(SocialPost.slot_date == date(2026, 10, 5))).all().count("facebook") == 0


def test_approval_mode_plans_drafts_that_never_publish_by_themselves(social, monkeypatch, db):
    monkeypatch.setenv("SOCIAL_REQUIRE_APPROVAL", "true")
    get_settings.cache_clear()
    service.plan(db, MONDAY)
    assert {p.status for p in db.scalars(select(SocialPost))} == {"draft"}
    assert service.publish_due(db, MONDAY + timedelta(days=9)) == 0 and publishers.FAKE_PUBLISHED == []


def test_only_connected_platforms_are_planned(social, monkeypatch, db):
    monkeypatch.setenv("SOCIAL_PLATFORMS", "instagram")
    get_settings.cache_clear()
    assert {p.platform for p in service.plan(db, MONDAY)} == {"instagram"}


def test_nothing_happens_when_the_provider_is_off(monkeypatch, db):
    monkeypatch.setenv("SOCIAL_PROVIDER", "none")
    get_settings.cache_clear()
    assert service.plan(db, MONDAY) == [] and service.run_due(db) == 0
    assert db.scalars(select(SocialPost)).all() == []
    get_settings.cache_clear()


def test_every_topic_is_used_before_one_repeats(social, db):
    seen = []
    for i in range(len(TOPICS)):
        t = service.next_topic(db)
        seen.append(t.key)
        db.add(SocialPost(platform="facebook", slot_date=date(2026, 1, 1) + timedelta(days=i), topic=t.key,
                          scheduled_for=datetime.now(UTC), status="published", caption="x", group_key="k"))
        db.commit()
    assert sorted(seen) == sorted(t.key for t in TOPICS)


def test_a_cancelled_slot_can_be_planned_again(social, db):
    first = service.plan_day(db, date(2026, 10, 5), now=MONDAY, platforms=["facebook"])[0]
    first.status = "cancelled"
    db.commit()
    again = service.plan_day(db, date(2026, 10, 5), now=MONDAY, platforms=["facebook"], topic_key="pricing")
    assert len(again) == 1 and again[0].topic == "pricing" and again[0].id != first.id


# --- publishing -----------------------------------------------------------------------------------------------------

def _plan_monday(db):
    service.plan(db, MONDAY)
    return MONDAY.replace(hour=20).astimezone(UTC)                      # after all of Monday's slots


def test_due_posts_are_published_with_public_image_urls(social, db):
    now = _plan_monday(db)
    assert service.publish_due(db, now) == 3
    rows = db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 5))).all()
    assert {p.status for p in rows} == {"published"} and all(p.external_id.startswith("fake-") for p in rows)
    sent = {x["platform"]: x for x in publishers.FAKE_PUBLISHED}
    assert [len(sent[p]["images"]) for p in PLATFORMS] == [1, 5, 5]
    assert all(u.startswith("https://api.dialogbot.test/api/v1/social/media/") and u.endswith(".jpg")
               for x in sent.values() for u in x["images"])
    assert service.publish_due(db, now) == 0                            # nothing is posted twice
    assert db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 7),
                                               SocialPost.status == "published")).all() == []


def test_a_post_is_not_published_before_its_time(social, db):
    service.plan(db, MONDAY)
    assert service.publish_due(db, MONDAY.astimezone(UTC)) == 0 and publishers.FAKE_PUBLISHED == []


def test_a_slot_that_is_hours_late_is_skipped_not_posted(social, monkeypatch, db):
    service.plan(db, MONDAY)
    monkeypatch.setenv("SOCIAL_MAX_LATE_MINUTES", "360")
    get_settings.cache_clear()
    assert service.publish_due(db, (MONDAY + timedelta(hours=21)).astimezone(UTC)) == 0   # Tuesday 03:00
    assert {p.status for p in db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 5)))} == {"skipped"}


def test_a_temporary_failure_is_retried_later_and_a_hard_one_is_not(social, db):
    publishers.FAKE_FAIL["facebook"] = PublishError("rate limit", retryable=True)
    publishers.FAKE_FAIL["instagram"] = PublishError("token udløbet", retryable=False)
    now = _plan_monday(db)
    service.publish_due(db, now)
    p = {x.platform: x for x in db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 5)))}
    assert (p["facebook"].status, p["facebook"].attempts) == ("scheduled", 1)
    assert p["facebook"].next_attempt_at > now and "rate limit" in p["facebook"].last_error
    assert (p["instagram"].status, p["instagram"].last_error) == ("failed", "token udløbet")
    assert p["tiktok"].status == "published"
    del publishers.FAKE_FAIL["facebook"]
    assert service.publish_due(db, now) == 0                            # still waiting for its retry time
    assert service.publish_due(db, now + timedelta(minutes=6)) == 1
    db.refresh(p["facebook"])
    assert p["facebook"].status == "published"


def test_retries_stop_after_three_attempts(social, db):
    publishers.FAKE_FAIL["facebook"] = PublishError("5xx", retryable=True)
    now = _plan_monday(db)
    for i in range(5):
        service.publish_due(db, now + timedelta(hours=i))
    fb = db.scalars(select(SocialPost).where(SocialPost.platform == "facebook", SocialPost.slot_date == date(2026, 10, 5))).one()
    assert (fb.status, fb.attempts) == ("failed", 3)


def test_a_post_stuck_in_publishing_is_reported_uncertain_never_retried(social, db):
    now = _plan_monday(db)
    p = db.scalars(select(SocialPost).where(SocialPost.platform == "tiktok", SocialPost.slot_date == date(2026, 10, 5))).one()
    p.status = "publishing"
    db.commit()
    db.execute(SocialPost.__table__.update().where(SocialPost.id == p.id).values(updated_at=now - timedelta(hours=1)))
    db.commit()
    service.publish_due(db, now)
    db.refresh(p)
    assert p.status == "failed" and "Usikkert" in p.last_error
    assert all(x["platform"] != "tiktok" for x in publishers.FAKE_PUBLISHED)


def test_unexpected_errors_are_not_retried(social, db, monkeypatch):
    monkeypatch.setattr(publishers.FakePublisher, "publish", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    now = _plan_monday(db)
    service.publish_due(db, now)
    assert {p.status for p in db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 5)))} == {"failed"}


def test_live_mode_refuses_a_non_https_public_url(social, monkeypatch, db):
    from app.core.errors import Conflict

    now = _plan_monday(db)
    post = db.scalars(select(SocialPost).where(SocialPost.platform == "facebook",
                                               SocialPost.slot_date == date(2026, 10, 5))).one()
    monkeypatch.setenv("SOCIAL_PROVIDER", "live")
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "t")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    get_settings.cache_clear()
    monkeypatch.setattr(publishers, "get_publisher", lambda db, platform: publishers.FakePublisher(platform))
    with pytest.raises(Conflict) as e:
        service.publish_one(db, post, now)
    assert e.value.code == "social_public_url" and publishers.FAKE_PUBLISHED == []


# --- operator API ---------------------------------------------------------------------------------------------------

def test_operator_api_flow_with_approval(social, monkeypatch, api, db):
    monkeypatch.setenv("SOCIAL_REQUIRE_APPROVAL", "true")
    get_settings.cache_clear()
    op = api.operator()
    assert api.c.get("/api/v1/operator/social", headers=api.h(api.user("almindelig@testmail.dk"))).status_code == 403
    r = api.post(op, "/operator/social/plan", {"day": "2099-01-01", "topic": "pricing"})
    assert r.status_code == 200, r.text
    created = r.json()["created"]
    assert {c["platform"] for c in created} == set(PLATFORMS) and {c["status"] for c in created} == {"draft"}
    fb = next(c for c in created if c["platform"] == "facebook")
    assert fb["topic"] == "pricing" and len(fb["images"]) == 1 and fb["link"].endswith("/priser")

    ov = api.c.get("/api/v1/operator/social", headers=api.h(op)).json()
    assert ov["provider"] == "fake" and ov["require_approval"] is True
    assert {"platform": "facebook", "status": "draft", "count": 1} in ov["counts"]

    r = api.c.patch(f"/api/v1/operator/social/posts/{fb['id']}", json={"caption": "Min egen tekst"}, headers=api.h(op))
    assert r.status_code == 200 and r.json()["caption"] == "Min egen tekst"
    assert api.post(op, f"/operator/social/posts/{fb['id']}/approve", {}).json()["status"] == "scheduled"
    assert api.post(op, f"/operator/social/posts/{fb['id']}/approve", {}).status_code == 409
    done = api.post(op, f"/operator/social/posts/{fb['id']}/publish-now", {})
    assert done.status_code == 200 and done.json()["status"] == "published"
    assert publishers.FAKE_PUBLISHED[-1]["caption"] == "Min egen tekst"

    ig = next(c for c in created if c["platform"] == "instagram")
    assert api.post(op, f"/operator/social/posts/{ig['id']}/cancel", {}).json()["status"] == "cancelled"
    assert api.c.patch(f"/api/v1/operator/social/posts/{ig['id']}", json={"caption": "x"}, headers=api.h(op)).status_code == 409
    listed = api.c.get("/api/v1/operator/social/posts?status=draft&platform=tiktok", headers=api.h(op)).json()["items"]
    assert [x["platform"] for x in listed] == ["tiktok"]
    assert api.post(op, "/operator/social/plan", {"topic": "pricing"}).status_code == 422
    assert api.post(op, "/operator/social/plan", {"day": "2099-01-02", "topic": "findes-ikke"}).status_code == 422


def test_images_are_served_publicly_by_unguessable_id_only(social, client, db):
    service.plan_day(db, date(2099, 1, 1), now=MONDAY, platforms=["facebook"])
    m = db.scalars(select(SocialMedia)).one()
    r = client.get(f"/api/v1/social/media/{m.id}.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == m.data
    for bad in (f"{m.id}.png", "1.jpg", "../x.jpg", f"{m.id}", "00000000-0000-0000-0000-000000000000.jpg"):
        assert client.get(f"/api/v1/social/media/{bad}").status_code == 404


# --- live platform calls (mocked transport) -------------------------------------------------------------------------

@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("SOCIAL_PROVIDER", "live")
    monkeypatch.setenv("META_PAGE_ID", "111")
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "SECRET-META-TOKEN")
    monkeypatch.setenv("META_INSTAGRAM_USER_ID", "222")
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "ck")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "cs")
    monkeypatch.setenv("TIKTOK_REFRESH_TOKEN", "rt-env")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.dialogbot.test")
    get_settings.cache_clear()
    monkeypatch.setattr(publishers, "_sleep", lambda s: None)
    publishers._page_token_cache.clear()
    calls: list[httpx.Request] = []
    handlers: list = []

    def transport(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        for match, reply in handlers:
            if match(req):
                return reply(req) if callable(reply) else reply
        return httpx.Response(404, json={"error": {"code": 100, "message": "unmocked " + req.url.path}})

    monkeypatch.setattr(publishers, "TRANSPORT", httpx.MockTransport(transport))
    yield SimpleNamespace(calls=calls, on=lambda m, r: handlers.append((m, r)))
    monkeypatch.setattr(publishers, "TRANSPORT", None)
    get_settings.cache_clear()


def _form(req: httpx.Request) -> dict:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(req.content.decode()).items()} if req.content else {}


def _post(platform, caption="Tekst", slides=None):
    return SocialPost(id=__import__("uuid").uuid4(), platform=platform, caption=caption,
                      slides=slides or [{"title": "Overskrift"}])


def test_live_provider_refuses_to_start_without_any_credentials():
    from app.config import Settings

    with pytest.raises(ValueError, match="SOCIAL_PROVIDER=live requires"):
        Settings(SOCIAL_PROVIDER="live", _env_file=None)


def test_fake_provider_is_refused_in_prod():
    from app.config import Settings

    with pytest.raises(ValueError, match="SOCIAL_PROVIDER=fake"):
        Settings(SOCIAL_PROVIDER="fake", APP_ENV="prod", SECRET_KEY="x" * 40, ENABLE_DEV_TOOLS=False,
                 EMAIL_ADAPTER="resend", RESEND_API_KEY="k", _env_file=None)


def test_facebook_photo_post(live, db):
    live.on(lambda r: r.url.path.endswith("/111/photos"), httpx.Response(200, json={"id": "9", "post_id": "111_9"}))
    res = publishers.FacebookPublisher().publish(db, _post("facebook", "Hej"), ["https://img/1.jpg"])
    assert (res.external_id, res.url) == ("111_9", "https://www.facebook.com/111_9")
    photos = next(c for c in live.calls if c.url.path.endswith("/111/photos"))
    f = _form(photos)
    assert (f["url"], f["caption"], f["published"], f["access_token"]) == ("https://img/1.jpg", "Hej", "true", "SECRET-META-TOKEN")
    assert photos.url.path.startswith("/v23.0/")


def test_a_system_user_token_is_exchanged_for_the_pages_own_token_once(live, db):
    """A System User token manages the Page but cannot post with it ("(#200) publish_actions"); the Page's own token
    (GET /{page}?fields=access_token) can. It is fetched once per process and used for every Meta call afterwards."""
    live.on(lambda r: r.method == "GET" and r.url.path.endswith("/111") and r.url.params.get("fields") == "access_token",
            httpx.Response(200, json={"access_token": "PAGE-TOKEN", "id": "111"}))
    live.on(lambda r: r.url.path.endswith("/111/photos"), httpx.Response(200, json={"id": "9", "post_id": "111_9"}))
    live.on(lambda r: r.method == "POST" and r.url.path.endswith("/222/media"), httpx.Response(200, json={"id": "c1"}))
    live.on(lambda r: r.method == "GET" and "status_code" in str(r.url), httpx.Response(200, json={"status_code": "FINISHED"}))
    live.on(lambda r: r.url.path.endswith("/222/media_publish"), httpx.Response(200, json={"id": "m1"}))
    publishers.FacebookPublisher().publish(db, _post("facebook", "Hej"), ["https://img/1.jpg"])
    publishers.InstagramPublisher().publish(db, _post("instagram", "Hej"), ["https://img/1.jpg"])
    lookups = [c for c in live.calls if c.url.path.endswith("/111") and c.url.params.get("fields") == "access_token"]
    assert len(lookups) == 1 and lookups[0].url.params["access_token"] == "SECRET-META-TOKEN"
    assert _form(next(c for c in live.calls if c.url.path.endswith("/111/photos")))["access_token"] == "PAGE-TOKEN"
    assert _form(next(c for c in live.calls if c.url.path.endswith("/222/media")))["access_token"] == "PAGE-TOKEN"


def test_instagram_carousel_creates_children_waits_then_publishes(live, db):
    seq = iter(["c1", "c2", "carousel"])
    live.on(lambda r: r.method == "POST" and r.url.path.endswith("/222/media"), lambda r: httpx.Response(200, json={"id": next(seq)}))
    live.on(lambda r: r.method == "GET" and "status_code" in str(r.url), httpx.Response(200, json={"status_code": "FINISHED"}))
    live.on(lambda r: r.url.path.endswith("/222/media_publish"), httpx.Response(200, json={"id": "m1"}))
    live.on(lambda r: r.url.path.endswith("/m1"), httpx.Response(200, json={"permalink": "https://instagram.com/p/x"}))
    res = publishers.InstagramPublisher().publish(db, _post("instagram", "Billedtekst"), ["https://img/1.jpg", "https://img/2.jpg"])
    assert (res.external_id, res.url) == ("m1", "https://instagram.com/p/x")
    creates = [_form(c) for c in live.calls if c.method == "POST" and c.url.path.endswith("/media")]
    assert creates[0]["is_carousel_item"] == "true" and creates[1]["is_carousel_item"] == "true"
    assert creates[2] == {"media_type": "CAROUSEL", "children": "c1,c2", "caption": "Billedtekst", "access_token": "SECRET-META-TOKEN"}
    assert _form(next(c for c in live.calls if c.url.path.endswith("media_publish")))["creation_id"] == "carousel"


def test_instagram_reports_a_processing_error_as_retryable(live, db):
    live.on(lambda r: r.method == "POST", httpx.Response(200, json={"id": "c1"}))
    live.on(lambda r: r.method == "GET", httpx.Response(200, json={"status_code": "ERROR"}))
    with pytest.raises(PublishError) as e:
        publishers.InstagramPublisher().publish(db, _post("instagram"), ["https://img/1.jpg"])
    assert e.value.retryable and "ERROR" in str(e.value)


@pytest.mark.parametrize("status,code,retryable", [(400, 190, False), (400, 368, False), (429, 4, True), (500, 2, True)])
def test_meta_errors_are_classified_and_never_leak_the_token(live, db, status, code, retryable):
    live.on(lambda r: True, httpx.Response(status, json={"error": {"code": code, "message": "Fejl hos Meta"}}))
    with pytest.raises(PublishError) as e:
        publishers.FacebookPublisher().publish(db, _post("facebook"), ["https://img/1.jpg"])
    assert e.value.retryable is retryable and "SECRET-META-TOKEN" not in str(e.value)


def test_a_timeout_on_the_final_call_is_uncertain_and_not_retried(live, db):
    def boom(r):
        raise httpx.ReadTimeout("slow", request=r)

    live.on(lambda r: True, boom)
    with pytest.raises(PublishError) as e:
        publishers.FacebookPublisher().publish(db, _post("facebook"), ["https://img/1.jpg"])
    assert e.value.retryable is False and "tjek profilen" in str(e.value)


def test_a_refused_connection_is_retryable(live, db):
    def refuse(r):
        raise httpx.ConnectError("nope", request=r)

    live.on(lambda r: True, refuse)
    with pytest.raises(PublishError) as e:
        publishers.FacebookPublisher().publish(db, _post("facebook"), ["https://img/1.jpg"])
    assert e.value.retryable is True


def _tiktok_mocks(live, privacy=("SELF_ONLY",), status="PUBLISH_COMPLETE", new_refresh="rt-rotated"):
    live.on(lambda r: r.url.path == "/v2/oauth/token/", httpx.Response(200, json={"access_token": "AT", "refresh_token": new_refresh}))
    live.on(lambda r: r.url.path.endswith("creator_info/query/"), httpx.Response(200, json={"data": {"privacy_level_options": list(privacy)}, "error": {"code": "ok"}}))
    live.on(lambda r: r.url.path.endswith("content/init/"), httpx.Response(200, json={"data": {"publish_id": "p1"}, "error": {"code": "ok"}}))
    live.on(lambda r: r.url.path.endswith("status/fetch/"), httpx.Response(200, json={"data": {"status": status, "fail_reason": "bad", "publicaly_available_post_id": ["v77"]}, "error": {"code": "ok"}}))


def test_tiktok_photo_post_and_rotating_refresh_token(live, db):
    _tiktok_mocks(live, privacy=("PUBLIC_TO_EVERYONE", "SELF_ONLY"))
    post = _post("tiktok", "Beskrivelse #dialogbot", [{"title": "Hook " * 40}])
    res = publishers.TikTokPublisher().publish(db, post, ["https://img/1.jpg", "https://img/2.jpg"])
    assert res.external_id == "v77" and res.note is None
    init = json.loads(next(c for c in live.calls if c.url.path.endswith("content/init/")).content)
    assert init["media_type"] == "PHOTO" and init["post_mode"] == "DIRECT_POST"
    assert init["source_info"] == {"source": "PULL_FROM_URL", "photo_cover_index": 0,
                                   "photo_images": ["https://img/1.jpg", "https://img/2.jpg"]}
    assert init["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE" and len(init["post_info"]["title"]) <= 90
    assert _form(next(c for c in live.calls if c.url.path.endswith("/oauth/token/")))["refresh_token"] == "rt-env"  # first use: env
    cred = db.get(SocialCredential, "tiktok")                           # the rotated token is stored encrypted
    assert b"rt-rotated" not in cred.secret_blob
    assert crypto.decrypt(crypto.Envelope(cred.key_version, cred.secret_blob), aad=b"social:tiktok") == b"rt-rotated"
    _tiktok_mocks(live, new_refresh="rt-third")
    publishers.TikTokPublisher().publish(db, post, ["https://img/1.jpg"])
    assert [_form(c)["refresh_token"] for c in live.calls if c.url.path == "/v2/oauth/token/"] == ["rt-env", "rt-rotated"]


def test_tiktok_unaudited_app_posts_privately_and_says_so(live, db):
    _tiktok_mocks(live, privacy=("SELF_ONLY",))
    res = publishers.TikTokPublisher().publish(db, _post("tiktok"), ["https://img/1.jpg"])
    assert "audit" in res.note


def test_tiktok_reports_a_rejected_post(live, db):
    _tiktok_mocks(live, status="FAILED")
    with pytest.raises(PublishError, match="afviste") as e:
        publishers.TikTokPublisher().publish(db, _post("tiktok"), ["https://img/1.jpg"])
    assert not e.value.retryable


def test_tiktok_error_codes_are_classified(live, db):
    live.on(lambda r: r.url.path == "/v2/oauth/token/", httpx.Response(200, json={"access_token": "AT"}))
    live.on(lambda r: r.url.path.endswith("creator_info/query/"), httpx.Response(200, json={"data": {}, "error": {"code": "ok"}}))
    live.on(lambda r: r.url.path.endswith("content/init/"), httpx.Response(200, json={"error": {"code": "rate_limit_exceeded", "message": "x"}}))
    with pytest.raises(PublishError) as e:
        publishers.TikTokPublisher().publish(db, _post("tiktok"), ["https://img/1.jpg"])
    assert e.value.retryable


def test_tiktok_without_credentials_is_not_connected(monkeypatch, db):
    monkeypatch.setenv("SOCIAL_PROVIDER", "live")
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "t")
    get_settings.cache_clear()
    assert publishers.live_configured(db) == {"facebook": False, "instagram": False, "tiktok": False}
    assert publishers.get_publisher(db, "tiktok") is None
    get_settings.cache_clear()


# --- housekeeping -----------------------------------------------------------------------------------------------------

def test_the_rolling_plan_does_not_undo_a_cancel(social, db):
    service.plan(db, MONDAY)
    tiktok = db.scalars(select(SocialPost).where(SocialPost.platform == "tiktok", SocialPost.slot_date == date(2026, 10, 5))).one()
    tiktok.status = "cancelled"
    db.commit()
    assert service.plan(db, MONDAY) == []                               # next minute's plan leaves the slot empty
    again = service.plan_day(db, date(2026, 10, 5), now=MONDAY, platforms=["tiktok"])   # only an explicit request re-plans
    assert len(again) == 1


def test_drafts_nobody_approved_in_time_expire(social, monkeypatch, db):
    monkeypatch.setenv("SOCIAL_REQUIRE_APPROVAL", "true")
    monkeypatch.setenv("SOCIAL_MAX_LATE_MINUTES", "360")
    get_settings.cache_clear()
    service.plan(db, MONDAY)
    service.publish_due(db, (MONDAY + timedelta(days=1)).astimezone(UTC))
    monday = db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 5))).all()
    assert {p.status for p in monday} == {"skipped"} and "godkendt" in monday[0].last_error
    assert {p.status for p in db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 7)))} == {"draft"}


def test_images_of_old_finished_posts_are_pruned_but_not_pending_ones(social, db):
    service.plan(db, MONDAY)
    service.publish_due(db, MONDAY.replace(hour=20).astimezone(UTC))
    old = datetime.now(UTC) - timedelta(days=60)
    db.execute(SocialPost.__table__.update().values(updated_at=old))
    db.commit()
    removed = service.prune_media(db)
    assert removed == 11                                                # Monday's published posts: 1 + 5 + 5
    left = {m.post_id for m in db.scalars(select(SocialMedia))}
    assert left == {p.id for p in db.scalars(select(SocialPost).where(SocialPost.status == "scheduled"))}


# --- insights: follower snapshots and engagement for the operator dashboard ------------------------------------------

def test_follower_snapshots_once_a_day_and_post_engagement(live, db):
    from app.models import SocialAccountSnapshot
    from app.modules.social import insights

    live.on(lambda r: r.method == "GET" and r.url.path.endswith("/111") and "followers_count" in str(r.url),
            httpx.Response(200, json={"followers_count": 120, "fan_count": 118, "name": "Dialogbot"}))
    live.on(lambda r: r.method == "GET" and r.url.path.endswith("/222") and "followers_count" in str(r.url),
            httpx.Response(200, json={"followers_count": 45, "follows_count": 3, "media_count": 7}))
    live.on(lambda r: r.url.path == "/v2/oauth/token/", httpx.Response(200, json={"access_token": "AT", "refresh_token": "rt-env"}))
    live.on(lambda r: r.url.path == "/v2/user/info/", httpx.Response(200, json={"data": {"user": {
        "follower_count": 9, "following_count": 1, "likes_count": 30, "video_count": 2}}}))
    now = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
    assert insights.snapshot_accounts(db, now=now) == 3
    assert insights.snapshot_accounts(db, now=now) == 0  # one row per day
    rows = {r.platform: r for r in db.scalars(select(SocialAccountSnapshot))}
    assert rows["facebook"].followers == 120 and rows["facebook"].likes == 118
    assert rows["instagram"].followers == 45 and rows["instagram"].posts == 7
    assert rows["tiktok"].followers == 9 and rows["tiktok"].likes == 30
    assert rows["tiktok"].captured_on == date(2026, 10, 8)
    # the TikTok call asked for the stats fields with the access token
    info = next(c for c in live.calls if c.url.path == "/v2/user/info/")
    assert info.method == "GET" and "follower_count" in str(info.url) and info.headers["Authorization"] == "Bearer AT"

    # engagement of published posts; a missing permission on one platform leaves an explanation, not a crash
    fb = SocialPost(platform="facebook", slot_date=date(2026, 10, 7), scheduled_for=now, status="published",
                    topic="pricing", group_key="g", caption="x", external_id="111_9", published_at=now)
    ig = SocialPost(platform="instagram", slot_date=date(2026, 10, 7), scheduled_for=now, status="published",
                    topic="pricing", group_key="g", caption="x", external_id="m1", published_at=now)
    db.add_all([fb, ig])
    db.commit()
    live.on(lambda r: r.url.path.endswith("/111_9"), httpx.Response(200, json={
        "likes": {"summary": {"total_count": 4}}, "comments": {"summary": {"total_count": 1}}, "shares": {"count": 2}}))
    live.on(lambda r: r.url.path.endswith("/m1"), httpx.Response(400, json={"error": {"code": 10, "message": "no permission"}}))
    assert insights.refresh_post_metrics(db, now=now) == 1
    db.refresh(fb), db.refresh(ig)
    assert fb.metrics == {"likes": 4, "comments": 1, "shares": 2} and fb.metrics_at == now
    assert "no permission" in ig.metrics["error"] and ig.metrics_at == now
    assert insights.refresh_post_metrics(db, now=now + timedelta(hours=1)) == 0  # fresh enough, not re-read


def test_dashboard_combines_followers_deltas_and_posts(social, monkeypatch, api, db):
    from app.models import SocialAccountSnapshot

    monkeypatch.setenv("SOCIAL_REQUIRE_APPROVAL", "true")
    get_settings.cache_clear()
    op = api.operator()
    today = datetime.now(CPH).date()
    for back, n in ((31, 100), (8, 110), (1, 118), (0, 120)):
        db.add(SocialAccountSnapshot(platform="facebook", captured_on=today - timedelta(days=back), followers=n, raw={}))
    db.add(SocialAccountSnapshot(platform="tiktok", captured_on=today, followers=None, raw={"error": "scope missing"}))
    db.commit()
    api.post(op, "/operator/social/plan", {"day": "2099-01-01", "topic": "pricing"})
    r = api.c.get("/api/v1/operator/social/dashboard?days=30", headers=api.h(op))
    assert r.status_code == 200, r.text
    d = r.json()
    fb = next(p for p in d["platforms"] if p["platform"] == "facebook")
    assert fb["followers"] == 120 and fb["delta_7d"] == 10 and fb["delta_30d"] == 20 and len(fb["series"]) == 3
    tt = next(p for p in d["platforms"] if p["platform"] == "tiktok")
    assert tt["followers"] is None and tt["error"] == "scope missing"
    assert {p["platform"] for p in d["pending"]} == set(PLATFORMS) and d["scheduled"] == [] and d["recent"] == []
    assert d["overview"]["require_approval"] is True
    assert api.c.get("/api/v1/operator/social/dashboard", headers=api.h(api.user("x@testmail.dk"))).status_code == 403
    assert api.post(op, "/operator/social/metrics/refresh", {}).status_code == 200  # fake provider: nothing to read


# --- profiles to follow ----------------------------------------------------------------------------------------------------

def test_social_links_keeps_profiles_and_drops_share_buttons():
    from app.modules.social.prospects import social_links

    html = """<a href="https://www.facebook.com/sharer/sharer.php?u=x">del</a>
    <a href='https://www.facebook.com/MalerfirmaetHansen'>fb</a>
    <a href="https://instagram.com/malerhansen/?hl=da">ig</a>
    <a href="https://www.tiktok.com/@malerhansen">tt</a>
    <a href="https://www.instagram.com/p/abc123/">et opslag</a>"""
    assert social_links(html) == {"facebook": "https://www.facebook.com/MalerfirmaetHansen",
                                  "instagram": "https://www.instagram.com/malerhansen",
                                  "tiktok": "https://www.tiktok.com/@malerhansen"}
    assert social_links("<p>ingen links</p>") == {}


def _cvr_hit(cvr, name, site, status="NORMAL", protected=False, code="433410"):
    return {"_source": {"Vrvirksomhed": {
        "cvrNummer": int(cvr), "reklamebeskyttet": protected,
        "virksomhedMetadata": {"nyesteNavn": {"navn": name}, "sammensatStatus": status,
                               "nyesteBeliggenhedsadresse": {"postnummer": 8000, "postdistrikt": "Aarhus C"},
                               "nyesteHovedbranche": {"branchekode": code, "branchetekst": "Malerforretninger"},
                               "nyesteKontaktoplysninger": ["+45 12345678", "mail@x.dk", site]}}}}


def test_prospects_batch_comes_from_cvr_and_the_websites_and_is_acted_on_once(social, monkeypatch, api, db):
    from app.modules.social import prospects

    monkeypatch.setenv("CVR_USERNAME", "u")
    monkeypatch.setenv("CVR_PASSWORD", "p")
    get_settings.cache_clear()
    hits = [_cvr_hit("10150817", "Maler Hansen ApS", "malerhansen.dk"),
            _cvr_hit("25313763", "Ophørt Maler", "gammel.dk", status="OPHØRT"),
            _cvr_hit("36214229", "Beskyttet Maler", "beskyttet.dk", protected=True),
            _cvr_hit("10103940", "Uden hjemmeside", ""),
            _cvr_hit("29910251", "Uden profiler", "ingenprofiler.dk")]
    posted = {}

    def fake_post(url, json, auth, timeout):
        posted["query"] = json
        return SimpleNamespace(status_code=200, json=lambda: {"hits": {"hits": hits}})

    sites = {"https://malerhansen.dk": {"facebook": "https://www.facebook.com/malerhansen",
                                        "instagram": "https://www.instagram.com/malerhansen"},
             "https://ingenprofiler.dk": {}}
    monkeypatch.setattr(prospects.httpx, "post", fake_post)
    added = prospects.discover(db, industry="haandvaerkere", fetch=lambda site: sites.get(site, {}))
    assert [p.cvr for p in added] == ["10150817"]
    assert added[0].facebook_url.endswith("/malerhansen") and added[0].tiktok_url is None
    assert added[0].city == "Aarhus C" and "håndværkere" in added[0].suggested_comment
    assert {"term": {"Vrvirksomhed.reklamebeskyttet": True}} in posted["query"]["query"]["function_score"]["query"]["bool"]["must_not"]
    # the same day never makes a second batch by itself, and a company is never suggested twice
    assert prospects.discover_if_due(db, now=datetime.now(CPH).replace(hour=9)) == 0
    assert prospects.discover(db, industry="haandvaerkere", fetch=lambda site: sites.get(site, {})) == []

    op = api.operator()
    d = api.c.get("/api/v1/operator/social/dashboard", headers=api.h(op)).json()
    assert d["prospects_enabled"] is True and [p["name"] for p in d["prospects"]] == ["Maler Hansen ApS"]
    pid = d["prospects"][0]["id"]
    r = api.post(op, f"/operator/social/prospects/{pid}/done", {"platforms": ["facebook", "facebook", "instagram"]})
    assert r.status_code == 200 and r.json()["acted_platforms"] == ["facebook", "instagram"]
    assert api.post(op, f"/operator/social/prospects/{pid}/skip", {}).status_code == 409
    assert api.c.get("/api/v1/operator/social/prospects?status=done", headers=api.h(op)).json()["items"][0]["cvr"] == "10150817"
    assert api.c.get("/api/v1/operator/social/dashboard", headers=api.h(op)).json()["prospect_counts"] == {"new": 0, "done": 1, "skipped": 0}
    assert api.c.get("/api/v1/operator/social/prospects", headers=api.h(api.user("y@testmail.dk"))).status_code == 403


def test_prospects_need_cvr_access(social, monkeypatch, api, db):
    from app.modules.social import prospects

    monkeypatch.delenv("CVR_USERNAME", raising=False)
    get_settings.cache_clear()
    assert prospects.discover(db) == []
    op = api.operator()
    assert api.post(op, "/operator/social/prospects/discover", {}).status_code == 501
    assert api.c.get("/api/v1/operator/social/dashboard", headers=api.h(op)).json()["prospects_enabled"] is False


# --- extra posts on demand -------------------------------------------------------------------------------------------------

def test_extra_posts_can_be_ordered_on_a_day_that_already_has_posts(social, api, db):
    service.plan(db, MONDAY)                                            # Monday is fully planned (and even published)
    for p in db.scalars(select(SocialPost).where(SocialPost.slot_date == date(2026, 10, 5))).all():
        p.status = "published"
    db.commit()
    created = service.create_extra(db, day=date(2026, 10, 5), topic_key="demo_call", platforms=["facebook", "instagram"],
                                   now=MONDAY)
    assert [p.platform for p in created] == ["facebook", "instagram"]
    assert all(p.extra and p.status == "draft" and p.topic == "demo_call" and p.slot_date == date(2026, 10, 5) for p in created)
    assert created[0].scheduled_for == MONDAY + timedelta(minutes=10)
    assert created[0].group_key.endswith(":extra")
    # the planner neither counts them nor replaces them
    assert service.plan(db, MONDAY) == []
    assert service.plan_day(db, date(2026, 10, 5), now=MONDAY, past_ok=True) == []
    # a later day: out at the normal slot time; a day in the past is refused
    later = service.create_extra(db, day=date(2026, 10, 6), platforms=["tiktok"], now=MONDAY)
    assert later[0].scheduled_for == service.slot_time(date(2026, 10, 6), "tiktok")
    with pytest.raises(ValidationFailed):
        service.create_extra(db, day=date(2026, 10, 4), now=MONDAY)
    # and the operator gets the same through the API, approving and publishing like any other draft
    op = api.operator()
    r = api.post(op, "/operator/social/extra", {"day": "2099-01-01", "topic": "chatbot", "platforms": ["tiktok"]})
    assert r.status_code == 200, r.text
    post = r.json()["created"][0]
    assert post["extra"] is True and post["status"] == "draft"
    assert api.post(op, f"/operator/social/posts/{post['id']}/approve", {}).json()["status"] == "scheduled"
    assert api.post(op, "/operator/social/extra", {"topic": "nope"}).status_code == 422
