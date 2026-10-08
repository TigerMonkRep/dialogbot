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
