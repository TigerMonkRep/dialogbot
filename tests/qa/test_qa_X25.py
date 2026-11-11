"""QA X25 (e2e-erhverv A, wave 2): no «Staging» label in the logged-in UI with production behaviour.

The web shell (web/src/components/shell.tsx:77) shows a badge only when GET /integrations/capabilities reports an
environment other than "prod", and the word «Staging» only for "staging". This proves the backend half: with
APP_ENV=prod every capability reports "prod" (→ no badge), and the production blueprint sets APP_ENV=prod on every
service even though the Render service names still say «staging»."""
from __future__ import annotations

import re
from pathlib import Path

from app.config import get_settings
from app.modules.integrations import registry

ROOT = Path(__file__).resolve().parents[2]


def test_prod_env_reports_prod_on_every_capability(monkeypatch):
    # Only the environment name changes (a full prod config needs real secrets, which QA never handles).
    prod = get_settings().model_copy(update={"app_env": "prod"})
    monkeypatch.setattr(registry, "get_settings", lambda: prod)
    envs = {c.environment for c in registry.capabilities()}
    assert envs == {"prod"}, envs


def test_render_blueprint_sets_app_env_prod_everywhere():
    text = (ROOT / "infra" / "render.yaml").read_text()
    values = re.findall(r"key: APP_ENV\s*\n\s*value:\s*([\w-]+)", text)
    assert values and set(values) == {"prod"}, values


def test_shell_hides_badge_for_prod_and_only_says_staging_for_staging():
    src = (ROOT / "web" / "src" / "components" / "shell.tsx").read_text()
    assert 'env && env !== "prod" &&' in src
    assert 'env === "staging" ? t("shell.envStaging")' in src
