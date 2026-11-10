"""QA X26 (integrations-qa): env var NAMES each integration needs are documented for every process that reads them.

Static check only – reads docs/environment-variables.md and infra/render.yaml, never an env value. The (name →
process) map below is traced by hand from the code; the `why` column is the code path, so a reviewer can verify it.
"""
from __future__ import annotations

import os
import re

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API, WORKER = "dialogbot-api-staging", "dialogbot-worker-staging"

# name -> (processes that read it in production, code path)
NEEDS: dict[str, tuple[tuple[str, ...], str]] = {
    "GOOGLE_OAUTH_CLIENT_ID": (("api", "worker"), "OAuth connect (API); token refresh in privat.calendar_sync via "
                                                 "connectors._fresh_secret → oauth.refresh (worker)"),
    "GOOGLE_OAUTH_CLIENT_SECRET": (("api", "worker"), "same as GOOGLE_OAUTH_CLIENT_ID"),
    "MICROSOFT_OAUTH_CLIENT_ID": (("api", "worker"), "same as GOOGLE_OAUTH_CLIENT_ID"),
    "MICROSOFT_OAUTH_CLIENT_SECRET": (("api", "worker"), "same as GOOGLE_OAUTH_CLIENT_ID"),
    "CREDENTIALS_KEY": (("api", "worker"), "credentials.get_secret (API + webhook delivery in worker)"),
    "TELEPHONY_PROVIDER": (("api", "worker"), "telephony.providers.providers(); platform.run_due_jobs in worker"),
    "TWILIO_ACCOUNT_SID": (("api", "worker"), "providers() (SMS connector, number provisioning in worker)"),
    "VAPI_API_KEY": (("api", "worker"), "campaigns.service.outbound_problem (dispatch runs in worker)"),
    "VAPI_SERVER_SECRET": (("api", "worker"), "webhook auth (API); campaigns.service.outbound_problem → dispatch "
                                             "in worker skips every campaign without it"),
    "STRIPE_SECRET_KEY": (("api", "worker"), "billing.stripe.configured(); invoice_due runs in worker"),
    "STRIPE_WEBHOOK_SECRET": (("api",), "webhooks/router.py stripe_webhook"),
    "RESEND_API_KEY": (("worker",), "email adapter in the worker (outbox)"),
    "RESEND_WEBHOOK_SECRET": (("api",), "webhooks/router.py resend"),
    "TRACK17_API_KEY": (("api", "worker"), "privat.parcels.tracker() (API + worker poll)"),
    "DUFFEL_ACCESS_TOKEN": (("api",), "privat.travel.providers()"),
    "TRAVELPAYOUTS_TOKEN": (("api",), "privat.travel.providers()"),
    "TRAVELPAYOUTS_MARKER": (("api",), "privat.travel.providers() (required together with the token)"),
    "SONIOX_API_KEY": (("api",), "stt bridge / Stemmetest"),
    "SONIOX_MODEL": (("api",), "config.py: Soniox model for bridge, engine and Stemmetest"),
}


def _docs() -> dict[str, str]:
    """name -> receiver column of its row in docs/environment-variables.md."""
    out: dict[str, str] = {}
    for line in open(os.path.join(ROOT, "docs/environment-variables.md"), encoding="utf-8"):
        if not line.startswith("| `"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        for name in re.findall(r"`([A-Z0-9_]+)`", cols[0]):
            out[name] = cols[2] if len(cols) > 2 else ""
    return out


def _render() -> dict[str, set[str]]:
    doc = yaml.safe_load(open(os.path.join(ROOT, "infra/render.yaml"), encoding="utf-8"))
    return {s["name"]: {e["key"] for e in s.get("envVars", [])} for s in doc["services"]}


@pytest.mark.parametrize("name", sorted(NEEDS))
def test_env_name_is_documented_for_every_process_that_reads_it(name):
    procs, why = NEEDS[name]
    docs, render = _docs(), _render()
    problems = []
    if name not in docs:
        problems.append("missing in docs/environment-variables.md")
    else:
        recv = docs[name].lower()
        for p in procs:
            if p not in recv:
                problems.append(f"docs receiver column {docs[name]!r} does not name {p}")
    for p in procs:
        svc = API if p == "api" else WORKER
        if name not in render[svc]:
            problems.append(f"not declared on {svc} in infra/render.yaml")
    assert not problems, f"{name} ({why}): " + "; ".join(problems)


def test_worker_fromservice_references_exist_on_the_api_service():
    """`fromService` copies a key the API service must declare; otherwise a blueprint sync has nothing to copy."""
    doc = yaml.safe_load(open(os.path.join(ROOT, "infra/render.yaml"), encoding="utf-8"))
    declared = {s["name"]: {e["key"] for e in s.get("envVars", [])} for s in doc["services"]}
    missing = []
    for s in doc["services"]:
        for e in s.get("envVars", []):
            ref = e.get("fromService")
            if ref and ref.get("envVarKey") and ref["envVarKey"] not in declared.get(ref["name"], set()):
                missing.append(f"{s['name']}.{e['key']} ← {ref['name']}.{ref['envVarKey']}")
    assert not missing, "fromService points at keys the source service does not declare: " + ", ".join(missing)
