# 5. Kørselsmanifest

Maskine: claude-dev (8 GB RAM, ingen swap), PostgreSQL 16 lokalt, Python venv /home/claude/venv, Node 22, Chromium (/opt/pw-browsers). Alle tider UTC, 12/11-2026. Kandidat-kode: origin/main 14edd47 + branch-commits (F-AUD26-01 i web/next.config.ts).

| # | Tid | Kommando (forkortet) | Miljø | Exit | Tal | Varighed | Evidens |
|---|---|---|---|---|---|---|---|
| 1 | 15:05 | `gh api …/actions/runs/43240805372,43240805270/jobs` | CI 14edd47 | – | 9/9 jobs success | – | qa/evidence/AUD26/ci-skips.txt |
| 2 | 15:08 | job-logs: pytest-summary | CI test-job | 0 | 2408 passed, 35 skipped, 48 xfailed | 22:49 | ci-skips.txt |
| 3 | 15:08 | job-logs: Playwright-tal pr. job | CI E2E | 0 | journeys 214 p/116 s; qa-cat 215/1, 62+10/150, 215/1, 64/148; privat 56+10+10/2 | – | ci-skips.txt |
| 4 | 15:10 | `ruff check …`, `alembic upgrade head`, `alembic check` | lokal, qa_audit26 | 0/0/0 | «All checks passed», «No new upgrade operations» | <1 min | static-checks.txt |
| 5 | 15:12–16:12 | `pytest` med `/home/claude/e2e-env.sh` i miljøet | lokal | 124 (timeout) | ~30 F/E – **miljøfejl**: e2e-env (PREVIEW_GATE, fake providers m.m.) ændrer test-antagelser + samtidig build/journeys-last. Kasseret som baseline; erstattet af #9 | 60 min | /home/claude/audit26/logs/baseline-pytest.log |
| 6 | 15:20 | `pytest tests/qa/test_qa_audit26_demo_call.py` | lokal, qa_audit26_t2 | 0 | 1 passed, 1 xfailed | 20 s | F-AUD26-02 |
| 7 | 15:38–15:41 | `npx tsc --noEmit`; `npm run i18n:check`; `npm run build` | lokal web (med F-AUD26-01) | 0/0/0 | `npm run lint` findes ikke (N/A) | 3 min | static-checks.txt |
| 8a | 15:41 | `curl -D -` mod lokal `next start` :3126 | lokal | – | 4 headers til stede | – | – |
| 8b | 15:43 | `playwright test e2e/security-headers.spec.ts` | lokal :3126 | 0 | 7 passed, 7 skipped (mobil = ved design) | 6 s | – |
| 8c | 15:44 | samme spec, `BASE_URL=https://dialogbot.app`, kun GET | produktion (main uden rettelse) | 1 | 7 failed – frame-ancestors mangler | 10 s | security-headers-before-prod.txt |
| 9 | 16:12–16:59 | `env -i … APP_ENV=test ENABLE_DEV_TOOLS=true DATABASE_URL/TEST_DATABASE_URL pytest -q --junitxml` (= CI-jobbets miljø) | lokal, qa_audit26_test | 0 | 2493 tests: 2410 passed, 34 skipped, 49 xfailed, 0 failed | 46:35 | pytest-junit.xml |
| 10 | 15:42–16:02 | `PW_SKIP_QA=1 npx playwright test` (= CI journeys) | lokal stak :8126/:3126, fake-udbydere | 0 | 344 tests: 221 passed, 123 skipped, 0 failed | 20:09 | journeys-summary.txt |
| 11 | 15:30, 15:39, 16:20 | read-only GET: /health/ready, /, /erhverv, /privat, /proev, /start, /priser, /login, /signup | produktion | – | ready: migration 0c1d5e7a9b3f = expected; Travelpayouts-markører 0 på alle sider; kun HSTS; 10×3 GET avg 0,44/0,61/0,65 s | – | prod-health-ready.json, prod-headers-before.txt, prod-latency-sample.txt |
| 12 | 16:10 | `python -m scripts.qa_audit_register docs/qa/2026-11-12-platform-audit` | repo | 0 | se report.md | 1 s | traceability.csv, findings-register.csv |

Unikke testcases vs. gentagelser: #9 er én kørsel (ingen retries). #10 kørt én gang, `retries: 0` i playwright.config. #8c er samme 7 cases som #8b mod et andet miljø.

**Ikke kørt på denne kandidat:** qa-catalog (e2e/qa, 4 shards) og privat-jobbet lokalt (CI-kørsel på 14edd47 bruges, uden F-AUD26-01); Privat-dybdekataloget (kræver qa_privat_stack – heller ikke i CI); voice-services/browser-worker-jobbene lokalt (CI grøn på 14edd47; ingen ændring i de mapper).
