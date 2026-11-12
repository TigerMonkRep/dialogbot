"""Provider sandbox tests: our real Stripe and Resend adapters against the providers' TEST surfaces.

Run by .github/workflows/provider-sandbox.yml (`pytest -m sandbox tests/sandbox`). Every test here carries the
`sandbox` marker and is skipped unless its provider key is in the environment, so the normal `pytest` (ci.yml) skips
them and stays offline:

- STRIPE_SECRET_KEY: Stripe TEST mode only. A key that does not start with sk_test_ / rk_test_ aborts the whole run
  before any Stripe call (never live mode).
- RESEND_API_KEY: mails go ONLY to Resend's test inboxes (delivered@resend.dev, bounced@resend.dev); every other
  recipient fails the test before anything is sent (see `resend_guard`).
- SANDBOX_REQUIRE_KEYS=1 (set by the workflow): a missing key fails instead of skipping, so a deleted or renamed
  GitHub secret cannot turn the job into a silent green "all skipped".

Key values are never printed: assertions and messages name the variable, not its content.
"""
from __future__ import annotations

import os

import pytest

STRIPE_TEST_PREFIXES = ("sk_test_", "rk_test_")
RESEND_TEST_RECIPIENTS = frozenset({"delivered@resend.dev", "bounced@resend.dev"})
_NEEDS = {"stripe": "STRIPE_SECRET_KEY", "resend": "RESEND_API_KEY"}


def _require_keys() -> bool:
    return os.environ.get("SANDBOX_REQUIRE_KEYS") == "1"


def pytest_collection_modifyitems(config, items):
    here = os.path.dirname(os.path.abspath(__file__))
    for item in items:
        if not str(item.fspath).startswith(here):
            continue
        item.add_marker(pytest.mark.sandbox)
        provider = next((p for p in _NEEDS if item.get_closest_marker(f"sandbox_{p}")), None)
        if provider and not os.environ.get(_NEEDS[provider]) and not _require_keys():
            item.add_marker(pytest.mark.skip(reason=f"{_NEEDS[provider]} er ikke sat (provider-sandbox-test)"))


@pytest.fixture(scope="session")
def stripe_test_key() -> None:
    """Fails (missing key with SANDBOX_REQUIRE_KEYS=1) or aborts the whole session (not a TEST-mode key)."""
    key = os.environ.get("STRIPE_SECRET_KEY") or ""
    if not key:
        pytest.fail("STRIPE_SECRET_KEY mangler (SANDBOX_REQUIRE_KEYS=1)")
    if not key.startswith(STRIPE_TEST_PREFIXES):
        pytest.exit("STRIPE_SECRET_KEY er ikke en Stripe TEST-nøgle (sk_test_/rk_test_) – afbryder, live mode røres aldrig",
                    returncode=1)


@pytest.fixture(scope="session")
def resend_test_key() -> None:
    if not os.environ.get("RESEND_API_KEY"):
        pytest.fail("RESEND_API_KEY mangler (SANDBOX_REQUIRE_KEYS=1)")


@pytest.fixture
def resend_guard(monkeypatch):
    """Every HTTP POST to Resend during the test must address only Resend's test inboxes – checked before the request
    leaves the process. Also blocks cc/bcc/reply_to fan-out."""
    import httpx

    real_post = httpx.post
    sent: list[dict] = []

    def guarded(url, *args, **kwargs):
        if "resend.com" in str(url):
            body = kwargs.get("json") or {}
            to = body.get("to")
            to = [to] if isinstance(to, str) else list(to or [])
            assert to and set(to) <= RESEND_TEST_RECIPIENTS, f"sandbox: modtager uden for Resends testadresser: {to}"
            assert not (body.get("cc") or body.get("bcc")), "sandbox: cc/bcc er ikke tilladt"
            sent.append({"to": to, "subject": body.get("subject")})
        return real_post(url, *args, **kwargs)

    monkeypatch.setattr(httpx, "post", guarded)
    return sent
