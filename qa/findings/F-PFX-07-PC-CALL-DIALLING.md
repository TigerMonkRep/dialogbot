---
id: F-PFX-07-PC-CALL-DIALLING
scenario: PC-CALL
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S1
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Ved en fejl hos Vapi, der ikke er en ApiError (harness-500 set af PB), blev et godkendt opkald stående i «dialling».

## Rettelse (udfyldes af fix-engineer)
- Rodårsag: calls.dial fangede kun ApiError fra campaigns.create_call. Status «dialling» var allerede committet.
- Rettelse: dial fanger alle fejl. En ikke-ApiError behandles som provider_error → _release: failed, credits frigives, opgaven går til «Prøv igen eller annullér» og kan prøves igen. no_response giver stadig «unknown» (der ventes på rapport, og der ringes aldrig op igen af sig selv).
- Filer: app/modules/privat/calls.py
- Test: tests/test_privat.py::test_provider_crash_never_leaves_the_call_dialling
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_provider_crash_never_leaves_the_call_dialling
- Fejler testen uden rettelsen? ja – «harness 500» på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: test_privat.py
- Dom: closed
