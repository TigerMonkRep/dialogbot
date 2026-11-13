"""Craft rules and the post trail ("forløb"): hook score, lint, humaniser, hashtag limits, the trail a post carries from
idea to publish, and the pipeline numbers on the operator dashboard."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.modules.social import content, craft, publishers
from app.modules.social.topics import PLATFORMS, TOPICS, TOPICS_BY_KEY


@pytest.fixture
def social(monkeypatch):
    monkeypatch.setenv("SOCIAL_PROVIDER", "fake")
    monkeypatch.setenv("SOCIAL_REQUIRE_APPROVAL", "true")
    monkeypatch.setenv("SOCIAL_PLATFORMS", "facebook,instagram,tiktok")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.dialogbot.test")
    get_settings.cache_clear()
    publishers.FAKE_PUBLISHED.clear()
    yield
    publishers.FAKE_PUBLISHED.clear()
    get_settings.cache_clear()


# --- hook score ------------------------------------------------------------------------------------------------------

def test_a_concrete_hook_beats_a_greeting_with_marketing_words():
    strong = craft.score_hook("Hvem tager telefonen, når du står midt i en opgave?")
    weak = craft.score_hook("Hej og velkommen til vores innovative løsning")
    assert strong.verdict == "stærk" and weak.verdict == "svag" and strong.score > weak.score
    assert any("hilsen" in f for f in weak.flags) and any("generisk" in f for f in weak.flags)


@pytest.mark.parametrize("text,formula", [
    ("Ringer din telefon, mens du har hænderne fulde?", "spørgsmål"),
    ("Stop med at miste kunder", "negativ kommando"),
    ("3 trin og din telefon passer sig selv", "tal"),
    ("Dit nummer. Din hverdag. Bare uden missede opkald.", "kontrast"),
])
def test_hook_formulas_are_recognised(text, formula):
    assert craft.score_hook(text).formula == formula


def test_the_preposition_i_does_not_count_as_addressing_the_reader():
    assert craft.score_hook("Opslag i dag").parts["henvendt"] < craft.score_hook("Din telefon").parts["henvendt"]


def test_no_hand_written_hook_is_rated_weak():
    # The hooks in topics.py were written for these platforms; the score is advice, so this pins the calibration only.
    weak = [(t.key, p, h) for t in TOPICS for p, h in t.hooks.items() if craft.score_hook(h).verdict == "svag"]
    assert weak == []


# --- humaniser and lint ----------------------------------------------------------------------------------------------

def test_humaniser_removes_invisible_characters_and_em_dashes_but_leaves_the_wording():
    text, changes = craft.humanize("Hej​ — dig  her")
    assert text == "Hej – dig her"
    assert {c["kind"] for c in changes} == {"usynlige tegn fjernet", "tankestreg ændret til dansk tankestreg", "dobbelte mellemrum"}
    assert craft.humanize("Helt almindelig tekst") == ("Helt almindelig tekst", [])


def test_stock_phrases_are_reported_never_rewritten():
    body = "I en verden hvor alt går hurtigt, tager vi telefonen."
    assert craft.humanize(body)[0] == body and craft.slop_flags(body) == ["i en verden hvor"]


def test_lint_follows_each_platforms_rules():
    findings = craft.lint("instagram", "x" * 130, ["a"] * 6, "Hej og velkommen")
    assert {f["code"] for f in findings} == {"hashtags", "first_line", "weak_hook"}
    assert [f["code"] for f in craft.lint("facebook", "Rolig tekst", ["a"] * 4)] == ["hashtags"]   # Facebook: 1-3
    assert [f["code"] for f in craft.lint("instagram", "Gem opslaget, hvis du kender en", ["a"] * 5)] == ["clean"]
    assert "engagement_bait" in {f["code"] for f in craft.lint("tiktok", "Like og del hvis du er enig", [])}


def test_x_is_ready_but_not_connected():
    assert craft.PLAYBOOKS["x"].connected is False and craft.PLAYBOOKS["x"].visible_chars == 280
    assert set(PLATFORMS) == {"facebook", "instagram", "tiktok"}          # nothing can be planned for X yet


def test_instagram_follows_the_ig_skills_and_the_others_the_social_media_skills():
    assert craft.PLAYBOOKS["instagram"].skillset == "ig-skills"
    assert {craft.PLAYBOOKS[p].skillset for p in ("facebook", "tiktok", "x")} == {"social-media-skills"}


@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.key)
def test_instagram_never_gets_more_than_five_hashtags(topic):
    assert len(content.hashtags_for("instagram", topic, ["a", "b", "c", "d", "e", "f"])) == 5
    assert len(content.template_draft("instagram", topic).hashtags) <= 5


# --- the trail on generated drafts ------------------------------------------------------------------------------------

def _ai_data(platform, hooks, caption="Tekst til opslaget."):
    n = {"facebook": 1, "instagram": 5, "tiktok": 5}[platform]
    slides = [{"title": "Hej og velkommen til vores innovative løsning" if i == 0 else f"{platform} {i}", "body": ""}
              for i in range(n)]
    return {"slides": slides, "hooks": hooks, "caption": caption, "hashtags": ["x"]}


def _completion(data):
    return SimpleNamespace(text=json.dumps(data), stop_reason="end_turn", served_model="test-model")


def _steps(d):
    return {s["step"]: s for s in d.trace}


def test_the_best_scoring_hook_candidate_is_used_and_the_trail_shows_all_of_them(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    hooks = ["Ringer din telefon, mens du har hænderne fulde?", "Pris: 999 kr. om måneden", "Vi er gratis og bedst"]
    data = {p: _ai_data(p, hooks) for p in PLATFORMS}
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _completion(data))
    d = {x.platform: x for x in content.generate(db, TOPICS_BY_KEY["missed_calls"])}["tiktok"]
    assert d.generator == "ai" and d.slides[0]["title"] == "Ringer din telefon, mens du har hænderne fulde?"
    steps = _steps(d)
    assert list(steps) == ["idea", "hooks", "copy", "checks"]
    cands = steps["hooks"]["detail"]["candidates"]
    assert [c["chosen"] for c in cands].count(True) == 1 and cands[0]["text"].startswith("Hej og velkommen")
    assert all("999" not in c["text"] and "gratis" not in c["text"] for c in cands)     # a price and a promise never compete
    assert steps["idea"]["detail"]["skillset"] == "social-media-skills"
    assert steps["copy"]["detail"]["generator"] == "ai" and steps["copy"]["detail"]["prompt_version"] == content.PROMPT_VERSION
    assert steps["checks"]["detail"]["facts"] == {"passed": True, "errors": []}
    get_settings.cache_clear()


def test_instagram_uses_the_ig_skills_in_its_trail(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    data = {p: _ai_data(p, []) for p in PLATFORMS}
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _completion(data))
    ig = {x.platform: x for x in content.generate(db, TOPICS_BY_KEY["booking"])}["instagram"]
    steps = _steps(ig)
    assert steps["idea"]["detail"]["skillset"] == "ig-skills"
    assert steps["hooks"]["status"] == "warn"            # the only candidate is a weak one: flagged, still posted as a draft
    get_settings.cache_clear()


def test_the_humaniser_cleans_ai_copy_and_the_trail_says_what_it_changed(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    data = {p: _ai_data(p, [], caption="Første sætning — anden sætning​.") for p in PLATFORMS}
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _completion(data))
    d = {x.platform: x for x in content.generate(db, TOPICS_BY_KEY["booking"])}["facebook"]
    assert "—" not in d.caption and "​" not in d.caption
    kinds = {c["kind"] for c in _steps(d)["checks"]["detail"]["humanize"]}
    assert kinds == {"usynlige tegn fjernet", "tankestreg ændret til dansk tankestreg"}
    get_settings.cache_clear()


def test_a_hand_written_post_says_why_the_ai_was_not_used(monkeypatch, db):
    # AI off by configuration
    off = {d.platform: d for d in content.generate(db, TOPICS_BY_KEY["pricing"])}
    for d in off.values():
        fb = _steps(d)["copy"]
        assert d.generator == "template" and fb["status"] == "ok" and fb["detail"]["fallback"] == {"code": "ai_off"}
        assert _steps(d)["hooks"]["detail"]["candidates"][0]["source"] == "skabelon"

    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    # the model's answer fails the facts guard for one platform
    data = {p: _ai_data(p, []) for p in PLATFORMS}
    data["instagram"]["caption"] = "Garanteret bedst."
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _completion(data))
    drafts = {d.platform: d for d in content.generate(db, TOPICS_BY_KEY["pricing"])}
    ig = _steps(drafts["instagram"])["copy"]
    assert drafts["instagram"].generator == "template" and ig["status"] == "warn" and ig["detail"]["fallback"]["code"] == "ai_rejected"
    assert any("forbidden phrase" in e for e in ig["detail"]["fallback"]["errors"])
    assert drafts["tiktok"].generator == "ai"

    # the model is unreachable
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _completion({}))
    monkeypatch.setattr(content, "parse_json", lambda t: (_ for _ in ()).throw(ValueError("ikke json")))
    for d in content.generate(db, TOPICS_BY_KEY["pricing"]):
        assert _steps(d)["copy"]["detail"]["fallback"]["code"] == "ai_unavailable"
    get_settings.cache_clear()


def test_the_prompt_carries_the_platform_rules_and_asks_for_three_hooks(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    seen = {}

    def fake(db, system, user):
        seen["system"] = system
        return SimpleNamespace(text="nej", stop_reason="end_turn", served_model="m")

    monkeypatch.setattr(content, "_complete", fake)
    content.generate(db, TOPICS_BY_KEY["pricing"])
    for p in ("instagram", "tiktok", "facebook"):
        assert all(rule in seen["system"] for rule in craft.PLAYBOOKS[p].rules)
    assert '"hooks"' in seen["system"] and "3-5 hashtags" in seen["system"] and "6-8 hashtags" not in seen["system"]
    get_settings.cache_clear()


# --- the trail on stored posts, through the operator API --------------------------------------------------------------

def test_the_trail_follows_a_post_from_idea_to_publish_and_the_dashboard_counts_it(social, api, db):
    op = api.operator()
    created = api.post(op, "/operator/social/plan", {"day": "2099-01-01", "topic": "pricing"}).json()["created"]
    assert len(created) == 3
    fb = next(c for c in created if c["platform"] == "facebook")
    assert [s["step"] for s in fb["pipeline"]] == ["idea", "hooks", "copy", "checks"]

    api.c.patch(f"/api/v1/operator/social/posts/{fb['id']}", json={"caption": "Min egen tekst"}, headers=api.h(op))
    api.post(op, f"/operator/social/posts/{fb['id']}/approve", {})
    done = api.post(op, f"/operator/social/posts/{fb['id']}/publish-now", {}).json()
    steps = [s["step"] for s in done["pipeline"]]
    assert steps == ["idea", "hooks", "copy", "checks", "edit", "approval", "publish"]
    edit, approval, publish = done["pipeline"][-3:]
    assert edit["detail"]["chars_after"] == len("Min egen tekst") and approval["detail"]["via"] == "godkend"
    assert publish["status"] == "ok" and publish["detail"]["external_id"]

    dash = api.c.get("/api/v1/operator/social/dashboard", headers=api.h(op)).json()
    total = dash["pipeline"]["total"]
    assert total["created"] == 3 and total["published"] == 1 and total["approved"] == 1 and total["template"] == 3
    assert set(dash["pipeline"]["platforms"]) == set(PLATFORMS)
    assert dash["pipeline"]["platforms"]["facebook"]["avg_hook_score"] is not None
    pending = {p["platform"]: p for p in dash["pending"]}
    assert set(pending) == {"instagram", "tiktok"} and pending["tiktok"]["pipeline"][0]["step"] == "idea"


def test_a_failed_publish_is_recorded_in_the_trail(social, api, db):
    op = api.operator()
    tt = next(c for c in api.post(op, "/operator/social/plan", {"day": "2099-01-01", "topic": "pricing"}).json()["created"]
              if c["platform"] == "tiktok")
    api.post(op, f"/operator/social/posts/{tt['id']}/approve", {})
    publishers.FAKE_FAIL["tiktok"] = publishers.PublishError("Afvist af TikTok", retryable=False)
    done = api.post(op, f"/operator/social/posts/{tt['id']}/publish-now", {}).json()
    assert done["status"] == "failed"
    last = done["pipeline"][-1]
    assert last["step"] == "publish" and last["status"] == "fail" and "Afvist" in last["detail"]["error"]
    assert last["detail"]["will_retry"] is False


def test_posts_made_before_the_trail_existed_simply_have_none(social, api, db):
    from sqlalchemy import select

    from app.models import SocialPost

    op = api.operator()
    api.post(op, "/operator/social/plan", {"day": "2099-01-01", "topic": "pricing"})
    for p in db.scalars(select(SocialPost)).all():
        p.pipeline = []
    db.commit()
    dash = api.c.get("/api/v1/operator/social/dashboard", headers=api.h(op)).json()
    assert all(p["pipeline"] == [] for p in dash["pending"])
    assert dash["pipeline"]["total"]["created"] == 3 and dash["pipeline"]["total"]["weak_hooks"] == 0
