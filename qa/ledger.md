# QA-ledger

Én linje pr. hændelse. Nyeste nederst.

| Tid | Fra → Til | Type | Emne | Kort |
|---|---|---|---|---|
| 11:40 | e2e-erhverv-B → qa-lead | finding | C09 C11 C15 M04 W04 W09 W12 W13 BK06 BK15 | 7 fund (1×S0, 2×S1, 3×S2, 1×S3); C09/M04/W04/W09/W13 not-implemented |
| 11:42 | qa-lead → fix-engineer | handoff | F-EB-01..07 | S0 genopkald-loop bekræftet i campaigns/service.py:322-330; batch 1 sendt |
| 11:42 | qa-lead → voice-qa | handoff | F-EB-05, F-EB-01 | Peter bekræfter booking selv ved kalenderfejl – tilføj eval-case |
| 11:42 | qa-lead → (Fürster) | needs-decision | C09 C15 M04 | Kampagner afregnes pr. opkald, ikke forudbetalte pakker – udgår kravene? |
| 12:07 | billing-qa → qa-lead | finding | B03 B04 B05 B06 X08 X28 | 10 fund F-BQ-001..010 (6×S1, 2×S2, 2×S3; 2 needs-decision); B03/B04/B05 not-implemented; tabel qa/billing/expected-vs-actual.md |
| 12:10 | integrations-qa → qa-lead | finding | E07 X26 | 8 fund F-IQ-01..08 (1×S1, 5×S2, 2×S3); E07 not-implemented; matrix qa/integrations/status.md |
| 12:20 | billing-qa → qa-lead | finding | B03-B06 X08 X28 | 10 fund (6×S1); B03/B04/B05 not-implemented; DB-001/002/003 regressionstests grønne |
| 12:22 | qa-lead → fix-engineer | handoff | F-BQ-002..010 | batch 2 (billing); F-BQ-001/005 needs-decision |
| 12:30 | integrations-qa → qa-lead | finding | E07 X26 | 8 fund (1×S1); E07 not-implemented; Fürster: tjek VAPI_SERVER_SECRET på worker |
| 12:33 | i18n-a11y-qa → qa-lead | finding | X24 | 8 sprog holder på 6 sider; 5 fund (funnel-fejl på dansk, kontrast, aria) |
| 12:35 | e2e-erhverv-A → qa-lead | finding | A01 A05 A06 S02 H01 M02 M03 M06 X01 | 10 fund (3×S1); X01/A05 pass; H01/M03/M06 not-implemented |
| 12:36 | qa-lead → fix-engineer | handoff | F-EA/F-IQ/F-LQ | batch 3; F-EA-04 needs-decision |
| 2026-11-10 | voice-qa → qa-lead | finding | X05 X15 X16 R02 R03 | F-VQ-01..09 + BK15-eval (F-EB-05 bekræftet i Peter-stien) |
| 12:20 | security-privacy → qa-lead | finding | X29 X20 | X29 IDOR-sweep 487/487 grøn (ingen krydslæsning/-skrivning); F-SQ-01 (dev-mailbox wildcard → operatør-overtagelse, S1), F-SQ-02 (DB-parametre inkl. argon2-hash i logs, S1), F-SQ-03 (M07 ikke bygget, S2) |
| 12:45 | voice-qa → qa-lead | finding | R02 R03 X05 X15 X16 | 9 fund (3×S1); X16 kræver live-test med Fürsters ja; ingen «privat preview» i prompts |
| 12:46 | qa-lead → fix-engineer | handoff | F-VQ-01..09 | batch 4 + create_call skal respektere TELEPHONY_PROVIDER=fake; F-VQ-05 needs-decision |
| 12:38 | Fürster → qa-lead | info | F-IQ-08 | VAPI_SERVER_SECRET sat på dialogbot-worker-staging og redeployet (produktion) |
| 2026-11-10 | fix-engineer → qa-lead, verifier | fix-ready | batch 1–5 | 43 fund rettet/delvist (se fundfilerne: Rodårsag/Rettelse/Testresultat); 3 migrationer b4d8e2f6a1c3, c5e9f3a7b2d4, d6f1a4b8c3e5; ikke committet |
| 13:05 | security-privacy → qa-lead | finding | X20 X29 | tenant-isolation pass (487/487 + 15.806 kald); 3 fund (2×S1) |
| 13:08 | e2e-privat → qa-lead | finding | X07 X09 X11 | X11 pass, reservationer hemmelige; 3 fund; Privat slået fra på fælles stak → separat stak |
| 15:10 | fix-engineer → qa-lead/verifier | fix-ready | 45 fund | batch 1-5 rettet; 3 migrationer; commit c3bed12 |
| 15:15 | qa-lead → verifier | handoff | alle fixed | gentest, before/after-bevis for S0/S1, fuld suite, journeys, CI-checks |
| 16:05 | verifier → qa-lead, fix-engineer | verdict | 48 fixed | 47 closed, 1 reopened (F-EA-07: docs/openapi.json ikke regenereret → CI rød); nye fund F-VR-01 (tidsafhængig test, rettet), F-VR-02 (needs-decision), F-VR-03 (idempotens-race → 500, flaky CI) |
| 2026-11-10 | fix-engineer → qa-lead, verifier | fix-ready | batch 6 | F-EA-07 (openapi regen), F-VR-03-X11 (insert-first idempotency, x11 10/10), F-PQ-02-X07 (hero-CTA → trial checkout); ikke committet |
| 16:30 | verifier → qa-lead, fix-engineer | verdict | batch 6 | F-VR-03 closed (10/10, 680 idem-tests), F-EA-07 closed (openapi cmp ok), F-PQ-02 reopened (anonym CTA → demo, account.tsx:43); nyt F-VR-04 (S3 stale-overtagelse) |
| 2026-11-10 | fix-engineer → qa-lead, verifier | fix-ready | batch 7 | F-PQ-02 (demo + ?plan → signup), F-VR-04-X11 (atomisk overtagelse + tests/test_idempotency.py); ikke committet |
| 17:05 | verifier → qa-lead | verdict | batch 7 | F-PQ-02 closed (X07 8/8 + anonym ?plan= → signup → checkout, uden ?plan= demo), F-VR-04 closed (test_idempotency 5×, trådet probe: én vinder) |
| 18:55 | qa-lead → Fürster | verdict | bølge 1 | GO: 0 åbne S0/S1, 51 fund lukket, CI grøn – merger PR #176 |
| 2026-11-10 | fix-engineer → qa-lead, verifier | fix-ready | beslutninger | F-EB-05-BK15 beslutning B (afventer bekræftelse, migration e7a2c5d9f1b3), F-VQ-05-X05 wont-fix; ikke committet |
| 2026-11-10 | fix-engineer → qa-lead | fix-ready | billing 1 | F-BQ-012-M04 (efterregistreret forbrug på næste faktura), F-BQ-011-B05 (pakke snapshot på aftalen, migration f3b8d1e6a4c2); ikke committet |
| 2026-11-10 | fix-engineer → qa-lead | fix-ready | prismodel A | Fælles minutpakke 300 min ind+ud, ingen opkaldsgebyr, overforbrug 1,50 ind / 2 kr. ud; migration a9c4e2f7b5d1; vilkår v1 uændret (needs-decision); ikke committet |
| 2026-11-10 | fix-engineer → qa-lead | fix-ready | B+C | Klage → kreditering (call_disputes, migration b6d2f8a3c7e9), Konto forbrug pr. opkald, operatør-fakturering M04, Konto læser egen aftale, ugeoversigt fra opgørelsen; ikke committet |
| 2026-11-10 | fix-engineer → qa-lead | fix-ready | prismodel A' | Opkaldspris efter pakken efter udfald (4/1/0,25 kr.) + 2 kr./min, migration c8e4a1f6d2b9, max_cost værste sag 14 kr./kontakt, tekster 8 sprog + vilkår v2; ikke committet |
| 2026-11-11 | fix-engineer #6 → qa-lead, verifier | fix-ready | F-VR-05..09 | 5d69023 (F-VR-05 en-pris med valuta), ba02bd8 (F-VR-06 tilbud/startdialog 4/1/0,25 kr. + påbegyndt, 8 sprog, vist = faktureret; F-VR-08 journey 22), 345f012 (F-VR-09 HTML+PDF via scripts/materiale-pdf.js), 52da47e (F-VR-07 docs + EUR 0,55 € undtagelse); journey 22 ikke kørt – verifier |
| 2026-11-11 | verifier #2 → qa-lead, fix-engineer #6 | verdict | F-VR-05..09 | 5 closed (revert til 7c17557: 3 regressionstests fejler, består på HEAD; journey 22 3/3 begge viewports; journeys.spec 64/64 fra ren db); nye fund F-VR-10-P05 (S3, tilbud «/min ind» uden «påbegyndt»), F-VR-11-X24 (S3, tilbuddets `notice` hårdkodet dansk, før-eksisterende) |
| 2026-11-10 | e2e-erhverv (C) → qa-lead | finding | bølge 2 P1 | F-E2C-01..11 (S1: 01 kun-kampagner kan ikke oprette, 02 «nej tak» ikke spærret, 03 import i kørende kampagne ringes op, 05 udløbet tilbud i prompt); K01 pass; C02-C14/K04 delvist not-implemented |
| 2026-11-11 | verifier → qa-lead, e2e-erhverv (D), fix-engineer | verdict | bølge 2 P1 | F-E2D-13-S03 closed (534a8a5; S03-pool 3/3, regressionstest fejler uden rettelsen); nye fund F-VER4-01-S03 (S3, pulje udtømmes af ~80 samtidige kald fra ét login) og F-VER4-02-P09 (S3, 5 px vandret scroll på juridiske sider, 390 px); pytest 1714/1714 + 41 xfail; e2e/qa 548 bestået ×2, flaky: X24 axe + S03-pool-widget |
