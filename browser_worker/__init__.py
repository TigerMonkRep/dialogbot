"""Dialogbot browser worker: a tethered browser agent for booking on external public booking pages.

The hard limits (network allow-list, forbidden fields, forbidden clicks, CAPTCHA/login detection, budgets) live in
CODE in this package, never in a prompt. See README.md and docs/ADR-004-browser-worker.md.
"""
