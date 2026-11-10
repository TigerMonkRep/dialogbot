---
id: F-PA-03-PC-APP-13
scenario: PC-APP-13
reported_by: e2e-privat (PA)
severity: S1
status: fixed
owner_fix: fix-engineer
related: [PC-APP-ABONNEMENTER-03]
---

## Kort
«Opsig Telia» skriver kun et brev, som brugeren selv skal sende. Alligevel markeres abonnementet straks «under opsigelse», og påmindelsen om sidste dag at opsige stopper. Har brugeren ikke sendt brevet, kører bindingen videre uden varsel.

## Trin til at genskabe
1. Slå Abonnementer til (prøve/Plus).
2. Chat: «Jeg har Telia til 199 kr. om måneden med binding til 2026-12-10» → «sidste dag at opsige: 10. november 2026 … Jeg minder dig om den sidste dag at opsige.»
3. Chat: «Opsig Telia» → brevet vises: «Send den fra din egen mail …».
4. Send ikke brevet. `GET /privat/apps/abonnementer/overview`: «Telia, 199 kr. pr. md., binding til 10. december 2026, **under opsigelse**».
5. `subs_app.due(data, 2026-11-04)` giver nu [] (før trin 3: påmindelsen «Sidste dag at opsige Telia er …»).

## Forventet
Koden selv (`chat.tool_cancel_subscription`): «the status changes only when the user sends the letter or the call is made – not on a proposal they may decline». Appens løfte i chatten: «Jeg minder dig om den sidste dag at opsige.» Fürster: Dialogbot gør intet på brugerens vegne uden godkendelse.

## Faktisk
Brevgrenen kalder `subs_app.mark_cancelling()` med det samme. `subs_app.due()` springer `status != "active"` over, så påmindelsen før sidste opsigelsesdag aldrig kommer. Oversigten og Mine apps siger «under opsigelse», selvom intet er sendt. En 60-årig vil tro, at Dialogbot har opsagt.

## Evidens
- qa/evidence/PC-APP-13/PA-letter-marks-cancelling.txt (live-stak :8400)
- Test: tests/qa/test_qa_pd_apps_a.py::test_pa_app13_letter_marks_cancelling_before_the_user_sends_it (fejler i dag)

## Forslag
Lad status være «active», indtil brugeren selv bekræfter («Jeg har sendt den» / en knap), eller lad påmindelsen køre for «cancelling» frem til sidste opsigelsesdag med teksten «Har du sendt opsigelsen af Telia?».

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest (e2e-privat PA, 2026-11-10): pytest qa_pd2 grøn; live :8400 på 451d53b – qa/evidence/PC-APP-13/PA-reverify-451d53b.txt: oversigten efter brevet er «Telia, 199 kr. pr. md., binding til 10. december 2026» (ingen «under opsigelse»). Browser-genkørsel afventer, at :3400 serverer sine chunks (500 kl. 23:04).
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
