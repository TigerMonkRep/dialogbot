---
id: F-PA-04-PC-APP-FLYTNING-03
scenario: PC-APP-FLYTNING-03
reported_by: e2e-privat (PA)
severity: S2
status: confirmed
owner_fix: fix-engineer
related: []
---

## Kort
Flytning minder om punkter, som brugeren allerede har krydset af på flyttelisten.

## Trin til at genskabe
1. Slå Flytning til. Chat: «Vi flytter til Odense den 2026-11-18» → listen «Flytning: Odense» med «Bestil flyttekasser og pakkemateriale (4. november 2026)».
2. Kryds punktet af (`POST /privat/tasks/{id}/items/{item}/toggle`).
3. Worker `app_kit.send_due` den 4. november kl. 10 → påmindelse «Flytning 18. november 2026: Bestil flyttekasser og pakkemateriale.» (push/e-mail i outbox).

## Forventet
Scenarie: «påmindelser pr. punkt». En påmindelse om noget, der er gjort, er støj – og lærer en travl bruger at ignorere dem.

## Faktisk
`moving.due()` regner kun ud fra `CHECKLIST` og flyttedagen. Den læser ikke listens `done`. Den samme fejl rammer punkter, brugeren har slettet fra listen.

## Evidens
- Test: tests/qa/test_qa_pd_apps_a.py::test_pa_flytning_reminds_items_the_user_already_ticked_off (fejler i dag)

## Forslag
Slå punktet op i listen (`_open_items`) i `due()`, og spring det over, hvis det er krydset af eller væk.
