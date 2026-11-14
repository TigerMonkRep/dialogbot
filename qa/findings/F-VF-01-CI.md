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

## Verifikation (verifier 2026-11-13 b, uafhængig)
- Kandidat: main 39a886f (39a886fe84d12ad261fd1afb27a9aa52e2df431e, ren worktree /home/claude/wt-ver1113b; alembic heads = d6f2a8c4e1b7, ét head)
- Separat spawnet verifier-agent. Rettelserne er ikke skrevet af mig. CI-lignende miljø (APP_ENV=test, ENABLE_DEV_TOOLS, egen DB qa_v1113b_test/qa_v1113b_rev), e2e-stak på egne porte 3437/8437 (DB qa_v1113b_e2e). Fuld pytest og CI på kandidaten: se ledger 2026-11-13 b.
- Gentest: `ruff check app tests scripts client voice_pipeline tts_service browser_worker` er grøn på kandidaten. De 8 xfail(strict)-markører med fund-id står i test_qa_pd_{billing,sec,core}.py. Fuld pytest: se ledger.
- Fejler testen uden rettelsen? ja. `ruff` på test_qa_pd_billing/sec/core.py fra d0244464^ fejler (2/5/1 fejl). Fra d0244464 er de grønne.
- Naboscenarier kørt: tests/qa/test_qa_pd_*.py (pd_sec alene: 66 passed, 5 xfailed)
- Dom: **closed**
- Bemærk: VF-01 blev rettet af en tidligere verifier (kun testfiler). Jeg er en anden agent end den.
