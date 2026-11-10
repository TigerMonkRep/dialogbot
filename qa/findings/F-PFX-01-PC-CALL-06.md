---
id: F-PFX-01-PC-CALL-06
scenario: PC-CALL-06
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S0
status: fixed
owner_fix: fix-engineer
related: []
---

## Kort
Et opkald godkendt «ved næste åbningstid» blev ringet op uden at tjekke igen, at app, telefon og plan stadig gjaldt.

## Rettelse (udfyldes af fix-engineer)
- Rodårsag: app/modules/privat/calls.py handle_call_due tjekkede kun status=scheduled og den gemte godkendelse.
- Rettelse: lige før opkaldet tjekker `_still_allowed` igen tre ting: «Ring for mig» er slået til, mobilnummeret er bekræftet, og – for et opkald betalt af planen – planen/prøveperioden gælder stadig. Holder det ikke, ringes der ikke (`_not_dialled`): status failed/result failed (tæller ikke i månedens opkald), credits frigives, opgaven går til «Prøv igen eller annullér», og brugeren får besked «Jeg ringede ikke til X: <grund>. Der er ikke brugt noget».
- Filer: app/modules/privat/calls.py
- Test: tests/test_privat_places_push.py::test_scheduled_call_checks_again_right_before_dialling[addon_off|phone_gone|trial_over] (fejler uden rettelsen, består med)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
