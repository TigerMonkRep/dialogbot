---
id: F-PX-08-PC-CALL-03
scenario: PC-CALL-03
reported_by: voice-qa (PX)
severity: S2
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Dobbeltklik på «Godkend» (parallelle POST /privat/calls/{id}/approve med samme Idempotency-Key) giver 500 (UniqueViolation) og 409 til to af fire kald. Der ringes stadig kun ét opkald, og kvoten tælles én gang – men brugeren kan se en fejl på et opkald, der faktisk er i gang.

## Trin
1. Plus-bruger med bekræftet mobil, opkaldsforslag.
2. Fire samtidige approve: nøgler px-0, px-1, px-0, px-1.

## Forventet
PC-CALL-03: «Præcis ét opkald … og én kvote-/credit-reservation»; svarene skal være 200 (replay) – aldrig 500.

## Faktisk
Svar 500, 200, 409, 200 (stak :8400 efter 451d53b, kørt 2 gange). pd-api.log: `{"error": "UniqueViolation", "sqlstate": "23505", "path": "/api/v1/privat/calls/13e0b996-…/approve", "event": "db.error"}` → status 500. /__qa/calls: præcis 1 opkald; task-events: én «Du godkendte opkaldet. Opkald 1 af 10 i Plus.» In-process-testen (TestClient, plan- og credits-sti) er grøn: ét opkald, én reservation.

## Evidens
- qa/evidence/PX/calls-stack-mobil-390.json, calls-stack-desktop-1440.json
- web/e2e/qa/privat-deep/x/voice-calls.spec.ts «PC-CALL-01/02/03»
- tests/qa/test_qa_pd_x.py::test_px_call_03_double_approve_parallel (grøn)

## Forslag
IdempotencyGuard: fang IntegrityError ved indsættelse af nøglen → 409 `idempotency_in_progress` (eller vent og returnér replay); web bør desuden deaktivere knappen ved første tryk.

## Rettelse (udfyldes af fix-engineer)
- Rodårsag: calls.approve læste opkaldet uden lås. Et parallelt kald (anden Idempotency-Key) ventede kun på profil-låsen og gik derefter videre med en forældet «proposed»-status, hvilket gav en anden reservation og en unique violation (500).
- Rettelse: approve låser PrivateCall-rækken (FOR UPDATE, populate_existing) og genlæser opgaven, før status tjekkes. Det parallelle kald ser «approved/dialling» og returnerer opgaven (200). Samme nøgle mens det første stadig kører giver 409 fra idempotensvagten – aldrig 500.
- Filer: app/modules/privat/calls.py
- Test: tests/qa/test_qa_pd_x.py::test_px_call_03_double_approve_parallel (+ assert «500 not in results»)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: Ingen 500 i pytest eller i 6 e2e-kørsler. Restsymptom: dobbeltklik med SAMME nøgle mens det første kald kører giver 409 (2/6 e2e) – dokumenteret valg i rettelsen; se F-VF-08
- Fejler testen uden rettelsen? nej – test_px_call_03 er også grøn på f2b3d11 (racen reproduceres ikke deterministisk)
- Naboscenarier kørt: e2e x/voice-calls.spec.ts
- Dom: closed
