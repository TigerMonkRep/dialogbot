"""Minimal, documented HTTP client for the Dialogbot API (stage 1).

This is NOT a frontend. It is the reproducible way to exercise the full
stage-1 journey against a running API and worker, and the reference for how a
real frontend must call the backend (routes, headers, error shape).

    from client.dialogbot_client import DialogbotClient
    c = DialogbotClient("http://localhost:8000")
    c.register("me@firma.dk", "LongPassword!2026", "Mig", signup_intent="reception")
    c.login("me@firma.dk", "LongPassword!2026")

Conventions
- Bearer token from POST /auth/login in the Authorization header.
- Every error body is {code, message, field_errors, request_id}; ApiError carries it.
- Effectful commands accept an Idempotency-Key header (invitations, approvals).
- Editable settings carry a `version`; PUT requires `expected_version` and
  returns 409 version_conflict when stale.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, status: int, body: dict[str, Any]):
        super().__init__(f"{status} {body.get('code')}: {body.get('message')}")
        self.status = status
        self.code = body.get("code")
        self.body = body


@dataclass
class DialogbotClient:
    base_url: str = "http://localhost:8000"
    token: str | None = None
    timeout: float = 10.0

    # --- plumbing ------------------------------------------------------------

    def _req(self, method: str, path: str, *, json: Any = None, params: dict | None = None,
             idempotency_key: str | None = None, auth: bool = True) -> Any:
        headers = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        r = httpx.request(method, f"{self.base_url}/api/v1{path}", json=json, params=params, headers=headers,
                          timeout=self.timeout)
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {"code": "http_error", "message": r.text}
            raise ApiError(r.status_code, body)
        if r.status_code == 204:
            return None
        return r.json()

    # --- health ----------------------------------------------------------------

    def ready(self) -> dict:
        return httpx.get(f"{self.base_url}/health/ready", timeout=self.timeout).json()

    # --- auth (A01–A04, S08) ---------------------------------------------------

    def register(self, email: str, password: str, display_name: str, signup_intent: str | None = None) -> dict:
        return self._req("POST", "/auth/register", json={"email": email, "password": password,
                                                          "display_name": display_name,
                                                          "signup_intent": signup_intent}, auth=False)

    def login(self, email: str, password: str) -> dict:
        out = self._req("POST", "/auth/login", json={"email": email, "password": password}, auth=False)
        self.token = out["access_token"]
        return out

    def logout(self) -> None:
        self._req("POST", "/auth/logout")
        self.token = None

    def me(self) -> dict:
        return self._req("GET", "/auth/me")

    def verify_email(self, token: str) -> dict:
        return self._req("POST", "/auth/verify-email", json={"token": token}, auth=False)

    def forgot_password(self, email: str) -> dict:
        return self._req("POST", "/auth/password/forgot", json={"email": email}, auth=False)

    def reset_password(self, token: str, password: str) -> dict:
        return self._req("POST", "/auth/password/reset", json={"token": token, "password": password}, auth=False)

    def dev_mailbox(self) -> list[dict]:
        """Dev-only simulated mailbox for the logged-in user's own address."""
        return self._req("GET", "/dev/mailbox")["items"]

    def wait_for_mail(self, subject_part: str, timeout_s: float = 15.0) -> dict:
        """Poll the simulated mailbox until the worker has delivered the mail."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            for m in self.dev_mailbox():
                if subject_part in m["subject"]:
                    return m
            time.sleep(0.5)
        raise TimeoutError(f"no mail containing {subject_part!r} within {timeout_s}s – is the worker running?")

    # --- workspaces (A05, A06, S02, S09) ----------------------------------------

    def create_workspace(self, name: str, product_intent: str | None = None) -> dict:
        return self._req("POST", "/workspaces", json={"name": name, "product_intent": product_intent})

    def list_workspaces(self) -> list[dict]:
        return self._req("GET", "/workspaces")

    def members(self, ws: str) -> list[dict]:
        return self._req("GET", f"/workspaces/{ws}/members")

    def change_role(self, ws: str, membership_id: str, role: str) -> dict:
        return self._req("PUT", f"/workspaces/{ws}/members/{membership_id}/role", json={"role": role})

    def invite(self, ws: str, email: str, role: str = "staff", idempotency_key: str | None = None) -> dict:
        return self._req("POST", f"/workspaces/{ws}/invitations", json={"email": email, "role": role},
                         idempotency_key=idempotency_key or str(uuid.uuid4()))

    def invitation_preview(self, token: str) -> dict:
        return self._req("GET", f"/invitations/{token}", auth=False)

    def accept_invitation(self, token: str) -> dict:
        return self._req("POST", "/invitations/accept", json={"token": token})

    def audit(self, ws: str, limit: int = 50) -> dict:
        return self._req("GET", f"/workspaces/{ws}/audit", params={"limit": limit})

    # --- business (O01, O03, O04, S01) --------------------------------------------

    def profile(self, ws: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/profile")

    def update_profile(self, ws: str, **fields) -> dict:
        current = self.profile(ws)
        payload = {k: current[k] for k in ("legal_name", "description", "website_url", "manual_setup", "cvr",
                                           "address_line", "postal_code", "city", "country", "timezone", "phone")}
        payload.update(fields)
        payload["expected_version"] = current["version"]
        return self._req("PUT", f"/workspaces/{ws}/profile", json=payload)

    def suggested_categories(self, ws: str) -> list[dict]:
        return self._req("GET", f"/workspaces/{ws}/categories/suggested")["items"]

    def add_category(self, ws: str, label: str, slug: str | None = None, is_primary: bool = False) -> dict:
        return self._req("POST", f"/workspaces/{ws}/categories", json={"label": label, "slug": slug,
                                                                       "is_primary": is_primary})

    def goals(self, ws: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/goals")

    def update_goals(self, ws: str, **fields) -> dict:
        current = self.goals(ws)
        payload = {k: current[k] for k in ("product_intent", "guidance_mode", "inbound_phone", "webchat", "callback",
                                           "booking", "conversation_goals")}
        payload.update(fields)
        payload["expected_version"] = current["version"]
        return self._req("PUT", f"/workspaces/{ws}/goals", json=payload)

    def languages(self, ws: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/languages")

    def update_languages(self, ws: str, **fields) -> dict:
        current = self.languages(ws)
        payload = {k: current[k] for k in ("interface_language", "default_conversation_language",
                                           "enabled_conversation_languages", "report_language")}
        payload.update(fields)
        payload["expected_version"] = current["version"]
        return self._req("PUT", f"/workspaces/{ws}/languages", json=payload)

    # --- knowledge (K01, K03, K04, K05) -------------------------------------------

    def knowledge_items(self, ws: str, kind: str | None = None) -> dict:
        return self._req("GET", f"/workspaces/{ws}/knowledge/items", params={"kind": kind} if kind else None)

    def create_knowledge(self, ws: str, kind: str, title: str, content: dict, source_ref: str | None = None) -> dict:
        return self._req("POST", f"/workspaces/{ws}/knowledge/items",
                         json={"kind": kind, "title": title, "content": content, "source_ref": source_ref})

    def new_draft(self, ws: str, item_id: str, title: str, content: dict) -> dict:
        return self._req("POST", f"/workspaces/{ws}/knowledge/items/{item_id}/drafts",
                         json={"title": title, "content": content})

    def edit_draft(self, ws: str, version_id: str, expected_edit_version: int, title: str, content: dict) -> dict:
        return self._req("PUT", f"/workspaces/{ws}/knowledge/versions/{version_id}",
                         json={"expected_edit_version": expected_edit_version, "title": title, "content": content})

    def submit(self, ws: str, version_id: str) -> dict:
        return self._req("POST", f"/workspaces/{ws}/knowledge/versions/{version_id}/submit")

    def approve(self, ws: str, version_id: str, idempotency_key: str | None = None) -> dict:
        return self._req("POST", f"/workspaces/{ws}/knowledge/versions/{version_id}/approve",
                         idempotency_key=idempotency_key or str(uuid.uuid4()))

    def reject(self, ws: str, version_id: str, reason: str) -> dict:
        return self._req("POST", f"/workspaces/{ws}/knowledge/versions/{version_id}/reject", json={"reason": reason})

    def review_queue(self, ws: str) -> list[dict]:
        return self._req("GET", f"/workspaces/{ws}/knowledge/review-queue")

    def assistant_knowledge(self, ws: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/assistant/knowledge")

    def offer_eligibility(self, ws: str, item_id: str, area_m2: float, on_date: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/knowledge/offers/{item_id}/eligibility",
                         params={"area_m2": area_m2, "on_date": on_date})

    # --- setup plan (G01–G08) -------------------------------------------------------

    def plan(self, ws: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/setup/plan")

    def task(self, ws: str, key: str) -> dict:
        return self._req("GET", f"/workspaces/{ws}/setup/tasks/{key}")

    def skip_task(self, ws: str, key: str) -> dict:
        return self._req("POST", f"/workspaces/{ws}/setup/tasks/{key}/skip")

    def assign_task(self, ws: str, key: str, user_id: str | None) -> dict:
        return self._req("PUT", f"/workspaces/{ws}/setup/tasks/{key}/assignee", json={"user_id": user_id})

    def run_check(self, ws: str, key: str) -> dict:
        return self._req("POST", f"/workspaces/{ws}/setup/checks/{key}/run")

    def run_all_checks(self, ws: str) -> dict:
        return self._req("POST", f"/workspaces/{ws}/setup/checks/run-all")

    def capabilities(self) -> list[dict]:
        return self._req("GET", "/integrations/capabilities")["items"]
