"""Outcomes of a browser run, as exceptions.

`ToolError` is recoverable (the LLM gets the message back and may try something else). Everything that subclasses
`RunOutcome` ends the tool loop: the runner maps it to a `browser_runs.status`.
"""
from __future__ import annotations


class ToolError(Exception):
    """A tool call that did not work (unknown ref, timeout, domain not allowed ...). Not fatal."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class RunOutcome(Exception):
    """Base for every terminal outcome. `status` is the browser_runs.status it maps to."""

    status = "failed"

    def __init__(self, error_code: str, message: str = "", details: dict | None = None):
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message or error_code
        self.details: dict = details or {}  # machine-readable context (url, screenshot, what was found ...)


class FallbackPhone(RunOutcome):
    """CAPTCHA, login, budget exceeded, or the agent cannot continue: hand over to the phone track."""

    status = "fallback_phone"


class ApprovalRequired(RunOutcome):
    """A click that commits (Bekræft/Book/Betal/Send ...) was attempted without a human yes."""

    status = "awaiting_approval"

    def __init__(self, label: str):
        super().__init__("approval_required", f"Kræver godkendelse: «{label}»")
        self.label = label


class RunFailed(RunOutcome):
    status = "failed"
