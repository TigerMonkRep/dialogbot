---
id: F-PK-02-PC-SUB-10
scenario: PC-SUB-10
reported_by: e2e-privat (PK)
severity: S2
status: new
owner_fix: fix-engineer
related: [F-PQ-01-X07]
---

## Kort
Et ukendt eller udløbet `session_id` i retur-URL'en (bogmærke, gammel mail, link sendt videre) giver `502 stripe_failed` med Stripe-teksten «Stripe afviste kaldet: No such checkout.session». Konto-siden viser den via `setError`, så brugeren får en teknisk 5xx-fejl i stedet for en venlig besked.

## Trin til at genskabe
1. Konto i prøveperiode. `GET /api/v1/privat/subscription?session_id=cs_test_findes_ikke`
2. Eller i browseren: `/privat/konto?abonnement=ok&session_id=cs_test_findes_ikke`

## Forventet
PC-SUB-10: «422 med field session_id; siden viser venlig fejl, ingen 500». Formatfejl giver allerede 422 (`abc`, 303 tegn).

## Faktisk
`502 {"code":"stripe_failed","message":"Stripe afviste kaldet: No such checkout.session"}` (qa/evidence/PC-SUB-10/PK-api-probe.txt). `sync_from_session` (subscriptions.py) lader Stripes 404 boble op som 502.

## Forslag
Fang Stripes `resource_missing` i `sync_from_session` og svar 404 `session_not_yours` eller 422 `session_id`, som ved en fremmed session. Siden viser så `plan.notCompleted`.

## Evidens
- qa/evidence/PC-SUB-10/PK-api-probe.txt
- Test: tests/qa/test_qa_pd_core.py::test_sub10_session_id_validation_never_5xx

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
