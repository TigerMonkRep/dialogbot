---
id: F-VF-01-CI
scenario: CI (lint + pytest) på qa/privat-deep
reported_by: verifier
severity: S1
status: closed
owner_fix: verifier (kun testfiler)
related: [F-PK-01-PC-SUB-08, F-PBQ-04-PC-SUB-13, F-PBQ-08-PC-ACC-04, F-PQ-03-X09]
---

## Kort
Branchen var rød i CI før PR: `ruff check` gav 30 fejl (kun i tests/qa/test_qa_pd_*.py), og fuld pytest havde 12 røde tests:
7 gap-tests for ÅBNE fund uden xfail-markør, 4 forældede tests (efter rettelser/beslutninger) og 1 harness-hul.

## Rettelse (verifier, kun test-/harnessfiler – ingen produktkode)
- ruff: 19 auto-rettelser + 11 manuelle (ubrugte variabler, zip(strict=False), noqa F811/B023 for pytest-fixtures). `ruff check …` grøn.
- xfail(strict=True) med fund-id: test_topup_refund_takes_the_amount_back (F-PBQ-05), test_ps_inv_05a (F-PS-02), test_ps_acc_05 (F-PS-10), test_ps_wish_11b (F-PS-06), test_ps_app_02b (F-PS-08), test_ps_pwa_03 (F-PS-09), test_sub10 (F-PK-02), test_pc_inv_08_referral_caps_hold (F-VF-04).
- Forældede tests tilpasset: test_pc_sub_13_ui (thenLine), test_pc_sub_14 (Privat sender nu egen dunning-mail, F-PBQ-08), test_pc_inv_08_self_referral (XPASS → markør fjernet).
- Harness tests/qa/qa_privat_stack.py: fake Stripe simulerer nu `DELETE /subscriptions/{id}` og sætter `amount_total` på betalte payment-sessioner (uden det gav enhver optankning i browseren `privat.topup_underpaid` og 0 kr.). test_sub08 tjekker levende abonnementer.
- e2e: brand-funnel PC-FUN-01 følger F-JP-01-flowet; app-suite «-01» åbner «Om appen»; voice-calls læser QA_PRIV_LOG.

## Evidens
tests/qa/test_qa_pd_{billing,sec,core}.py grønne efter (xfail som forventet); apps_a/apps_b/x 179 passed, 2 skipped.

## Verifikation (udfyldes af verifier)
- Verifier 2026-11-13 (uafhængig, start forfra), main 5c75ea3; stak :3336/:8336, DB qa_ver1112*; logs i /home/claude/ver1112/logs.
- Gentest: `ruff check app tests scripts client voice_pipeline tts_service browser_worker` → «All checks passed!» på main
  5c75ea3; GitHub `test`-jobbet (ruff + alembic + fuld pytest + kontrakt-cmp) er grønt på main 5c75ea3 og på 587e648.
- Fejler uden rettelsen? **Ja**: på 15c3704 (= d024446^) giver samme ruff-kommando «Found 30 errors» (som fundet beskriver).
- Naboscenarier: hele CI-matrixen på main 5c75ea3: test, voice-services, browser-worker, journeys, qa-catalog 1–4,
  privat grønne. **Undtagelse:** provider-sandbox (nyt i #208) er rød – nyt fund F-VER1112-03-CI (konfiguration, ikke
  denne rettelse).
- Dom: **closed**
