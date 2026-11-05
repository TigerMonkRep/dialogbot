"""A disabled browser worker must stay up without any other setting (Render: the service exists from the blueprint, the flag is
flipped later), and an enabled one must fail loudly and at once when its settings are missing."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from browser_worker import runner

ROOT = Path(__file__).resolve().parents[2]


def clean_env(**extra) -> dict:
    """The environment of a freshly created Render service: no DATABASE_URL, no SECRET_KEY, nothing but the basics."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "SYSTEMROOT", "TMPDIR")}
    env.update({"PYTHONPATH": str(ROOT), "APP_ENV": "staging", "PYTHONUNBUFFERED": "1"}, **extra)
    return env


@pytest.mark.parametrize("value,expected", [("true", True), ("True", True), ("1", True), (" yes ", True), ("on", True),
                                            ("false", False), ("0", False), ("", False), ("nej", False), ("truee", False)])
def test_flag_is_read_like_the_settings_read_it(value, expected):
    assert runner.enabled_in_env({"BROWSER_WORKER_ENABLED": value}) is expected
    assert runner.enabled_in_env({}) is False


def test_a_disabled_worker_idles_without_database_or_secrets():
    p = subprocess.Popen([sys.executable, "-m", "browser_worker.runner"], env=clean_env(), cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(6)
        assert p.poll() is None, "the worker exited: Render would restart-loop it"
    finally:
        p.terminate()
    out, _ = p.communicate(timeout=15)
    assert "browser_worker.disabled" in out and "ValidationError" not in out and "Traceback" not in out


def test_an_enabled_worker_without_its_settings_fails_at_once_and_says_why():
    p = subprocess.run([sys.executable, "-m", "browser_worker.runner"], env=clean_env(BROWSER_WORKER_ENABLED="true"), cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    assert "DATABASE_URL" in p.stdout + p.stderr           # the missing setting is named, nothing is started half-configured
