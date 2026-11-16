"""Short-form video: the manuscript, the five-point score, the budget guard, the learning loop and the operator API."""
from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.modules.social import content, video
from app.modules.social.topics import TOPICS, TOPICS_BY_KEY

WEAK = {
    "duration": 50, "persona": "ai_person",
    "hook": {"spoken": "Hej og velkommen til vores innovative løsning", "on_screen": "", "visual": "", "motion": "", "end": 6},
    "beats": [{"role": "value", "start": 6, "end": 50, "spoken": "øh altså Dialogbot er sådan set bedst " + "og ligesom meget mere " * 8,
               "on_screen": "", "visual": "", "cut": "klip"}],
    "cta": {"spoken": "", "on_screen": "", "ask": ""}, "save_asset": "", "caption": "", "hashtags": [], "disclosure": "AI-genereret",
}


def _norm(raw, formula="story_arc", persona="ai_person"):
    return video.normalise(raw, topic=TOPICS_BY_KEY["pricing"], formula=formula, persona=persona)


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- the score ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("topic", TOPICS, ids=lambda t: t.key)
@pytest.mark.parametrize("formula", video.FORMULAS)
def test_every_hand_written_brief_passes_the_facts_guard_and_scores_well(topic, formula):
    b = video.template_brief(topic, formula)
    assert video.problems(b) == []
    s = video.score_brief(b)
    assert s.total >= 75 and all(c["score"] >= 60 for c in s.criteria.values()), s.as_dict()
    assert b["hook"]["end"] <= video.HOOK_SECONDS and b["disclosure"] == "AI-genereret"
    assert all(x["end"] - x["start"] <= 4.5 for x in b["beats"]) and 15 <= b["duration"] <= 35


def test_a_weak_brief_is_told_exactly_what_is_missing():
    s = video.score_brief(_norm(WEAK))
    assert s.verdict == "svag" and s.total < 50
    first3 = " ".join(s.criteria["first3"]["notes"])
    assert "tekst på skærmen" in first3 and "bevægelse" in first3 and "længere end 3 sekunder" in first3
    assert any("Fyldord" in n for n in s.criteria["pace"]["notes"])
    assert any("Længden" in n for n in s.criteria["pace"]["notes"])
    assert any("gemme" in n for n in s.criteria["share"]["notes"])
    assert s.flags and all(k in s.criteria for k in video.CRITERIA)


def test_each_formula_checks_its_own_parts():
    b = video.template_brief(TOPICS_BY_KEY["pricing"], "tool_outcome_time")
    b["beats"] = [x for x in b["beats"] if "Dialogbot" not in x["spoken"] and "halv time" not in x["spoken"]]
    b["hook"]["spoken"] = "Ringer din telefon?"
    b["cta"]["spoken"] = "Send den videre"
    notes = video.score_brief(b).criteria["concept"]["notes"]
    assert "Navngiv værktøjet" in notes and "Sig hvor hurtigt det går" in notes
    story = video.template_brief(TOPICS_BY_KEY["pricing"], "story_arc")
    story["beats"] = [x for x in story["beats"] if x["role"] != "payoff"]
    assert any("payoff" in n for n in video.score_brief(story).criteria["concept"]["notes"])


def test_the_facts_guard_rejects_prices_promises_links_and_a_missing_ai_label():
    b = video.template_brief(TOPICS_BY_KEY["pricing"], "story_arc")
    b["beats"][1]["spoken"] = "Det koster 2.495 kr. og vi garanterer det bedste, se https://x.dk"
    b["disclosure"] = ""
    errs = video.problems(b)
    assert {"pris", "garanter", "bedst", "link", "mangler AI-mærkning"} <= set(errs)
    real = video.template_brief(TOPICS_BY_KEY["pricing"], "story_arc", persona="rigtig_person")
    assert real["disclosure"] == "" and video.problems(real) == []


# --- budget ------------------------------------------------------------------------------------------------------------

def test_the_cost_estimate_uses_the_price_per_second_the_retries_and_the_exchange_rate():
    assert video.estimate_cost_dkk(23) == round(23 * 0.10 * 1.3 * 6.9, 2)
    assert 15 <= video.estimate_cost_dkk(23) <= 25  # about 20 kr. per video, so roughly 25 videos fit in 500 kr.


# --- learning ----------------------------------------------------------------------------------------------------------

def test_engagement_weighs_sends_and_saves_above_likes_and_needs_views():
    assert video.engagement({"likes": 50}) is None
    base = video.engagement({"views": 1000, "likes": 50})
    assert video.engagement({"views": 1000, "shares": 50}) > video.engagement({"views": 1000, "saves": 50}) > base


def test_learning_ranks_formulas_and_every_formula_is_tested_before_one_is_favoured():
    rows = [{"formula": "story_arc", "hook_formula": "spørgsmål", "engagement": e} for e in (5, 6, 7)]
    rows += [{"formula": "myth_buster", "hook_formula": "tal", "engagement": e} for e in (1, 1, 2)]
    rows += [{"formula": "myth_buster", "hook_formula": "tal", "engagement": None}]
    learned = video.learn(rows)
    assert [f["key"] for f in learned["formulas"]] == ["story_arc", "myth_buster"] and learned["measured"] == 6
    # two formulas still lack samples: they are tried first, whatever the winner is
    assert set(video.choose_formulas(4, learned, random.Random(1))) == {"tool_outcome_time", "relatable_stakes"}
    full = video.learn(rows + [{"formula": f, "hook_formula": "x", "engagement": 3} for f in ("tool_outcome_time", "relatable_stakes") for _ in range(3)])
    picks = video.choose_formulas(400, full, random.Random(2))
    assert picks.count("story_arc") > 250  # the winner mostly
    assert all(picks.count(f) > 5 for f in video.FORMULAS)  # but nobody is locked out


# --- the AI brief --------------------------------------------------------------------------------------------------------

def _ai(brief):
    import json
    return SimpleNamespace(text=json.dumps(brief), model="fake-model")


def test_an_ai_brief_is_used_when_it_passes_and_replaced_by_the_template_when_it_does_not(monkeypatch, db):
    monkeypatch.setenv("AI_PROVIDER", "fake")
    get_settings.cache_clear()
    topic = TOPICS_BY_KEY["pricing"]
    good = video.template_brief(topic, "story_arc")
    good["hook"]["spoken"] = "Hvad koster en AI-receptionist egentlig?"
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _ai(good))
    b, note = video.generate_brief(db, topic, "story_arc")
    assert note == {"generator": "ai", "model": "fake-model"} and b["hook"]["spoken"].startswith("Hvad koster")
    assert b["disclosure"] == "AI-genereret"

    bad = video.template_brief(topic, "story_arc")
    bad["beats"][0]["spoken"] = "Garanteret den bedste løsning til 99 kr."
    monkeypatch.setattr(content, "_complete", lambda db, system, user: _ai(bad))
    b, note = video.generate_brief(db, topic, "story_arc")
    assert note["generator"] == "template" and note["fallback"]["code"] == "ai_rejected" and "pris" in note["fallback"]["errors"]
    assert video.problems(b) == []

    def boom(db, system, user):
        raise RuntimeError("nede")
    monkeypatch.setattr(content, "_complete", boom)
    assert video.generate_brief(db, topic, "story_arc")[1]["fallback"]["code"] == "ai_unavailable"
    monkeypatch.setenv("AI_PROVIDER", "none")
    get_settings.cache_clear()
    assert video.generate_brief(db, topic, "story_arc")[1]["fallback"] == {"code": "ai_off"}


# --- API ---------------------------------------------------------------------------------------------------------------

def test_plan_approve_reject_and_the_budget_through_the_operator_api(api, db, monkeypatch):
    monkeypatch.setenv("VIDEO_MONTHLY_BUDGET_DKK", "45")  # room for two videos of about 21 kr.
    get_settings.cache_clear()
    op = api.operator()
    created = api.post(op, "/operator/social/videos/plan", {"count": 3}).json()["created"]
    assert len(created) == 3 and len({c["topic"] for c in created}) == 3
    assert {c["formula"] for c in created} <= set(video.FORMULAS) and all(c["status"] == "draft" and c["score"]["total"] >= 75 for c in created)

    first = api.post(op, f"/operator/social/videos/{created[0]['id']}/approve", {}).json()
    assert first["status"] == "approved"
    api.post(op, f"/operator/social/videos/{created[1]['id']}/approve", {})
    over = api.post(op, f"/operator/social/videos/{created[2]['id']}/approve", {})
    assert over.status_code == 409 and "Budgettet rækker ikke" in over.text
    assert api.post(op, f"/operator/social/videos/{created[2]['id']}/reject", {}).json()["status"] == "rejected"
    again = api.post(op, f"/operator/social/videos/{created[0]['id']}/approve", {})
    assert again.status_code == 409

    ov = api.c.get("/api/v1/operator/social/videos", headers=api.h(op)).json()
    assert ov["budget"]["monthly_dkk"] == 45 and 40 < ov["budget"]["committed_dkk"] < 45
    assert ov["rendering_connected"] is False and len(ov["items"]) == 3 and ov["learning"]["measured"] == 0


def test_only_operators_may_use_the_video_endpoints(api):
    r = api.c.get("/api/v1/operator/social/videos")
    assert r.status_code in (401, 403)
