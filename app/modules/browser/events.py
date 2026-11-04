"""Outbox event types of the browser worker. The main worker (app/worker/runner.py) must NOT claim these: they are driven
by the separate browser worker process (browser_worker/runner.py), which holds the live Playwright sessions."""
EVENT_RUN = "privat.browser_run"
EVENT_DECISION = "privat.browser_decision"
BROWSER_EVENT_TYPES = (EVENT_RUN, EVENT_DECISION)
