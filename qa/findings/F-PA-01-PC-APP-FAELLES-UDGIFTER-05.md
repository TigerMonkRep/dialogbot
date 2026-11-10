---
id: F-PA-01-PC-APP-FAELLES-UDGIFTER-05
scenario: PC-APP-FAELLES-UDGIFTER-05
reported_by: e2e-privat (PA)
severity: S1
status: confirmed
owner_fix: fix-engineer
related: [PC-APP-FLYTNING-05, PC-ACC-02]
---

## Kort
«Slet appens data» for Fælles udgifter og Flytning siger «Sletter alt, hvad {name} har gemt», men listerne appen selv har oprettet («Udgifter: <gruppe>» med beløb og vennernes navne, «Flytning: <by>» med 12 punkter) bliver liggende.

## Trin til at genskabe
1. Plus/prøve-konto. Slå Fælles udgifter til.
2. Chat: «Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, Bo og mig» → appen opretter listen «Udgifter: sommerhuset».
3. Slå appen fra → appens side → «Slet appens data» → «Ja, slet» (`DELETE /privat/addons/faelles-udgifter/data` → 200, deleted=1).
4. `GET /privat/tasks`: «Udgifter: sommerhuset» med «Mette: 1.200 kr. – mad» findes stadig (og ligger i Opgaver).
5. Det samme for Flytning: «Vi flytter til Odense den 2027-04-01» → slå fra → slet data → «Flytning: Odense» med 12 punkter findes stadig.

## Forventet
UI-teksten `apps.deleteText` / `apps.deleteConfirm`: «Sletter alt, hvad {name} har gemt. Det kan ikke fortrydes.» Scenarie PC-APP-*-05: «Data slettes via «Slet data» → rækker væk … geninstallér → tom tilstand med Trin 1».

## Faktisk
`app_status._data_tables()` sletter kun `private_app_data` for nøglen. Opgaven (`private_tasks` + items), som `expenses.add_expense` og `moving.plan` opretter via `service.create_digital`, røres ikke. Hvis listen er delt med vennerne, kan de stadig se beløbene. Når appen slås til igen og brugeren skriver et nyt udlæg i «sommerhuset», kommer der en ny liste med samme titel ved siden af den gamle.

## Evidens
- qa/evidence/PC-APP-FAELLES-UDGIFTER-05/PA-delete-data-leaves-list.txt (live-stak :8400)
- Test: tests/qa/test_qa_pd_apps_a.py::test_pa_delete_data_removes_the_lists_the_app_made (fejler i dag)
- Test: web/e2e/qa/privat-deep/apps-a/faelles-udgifter.spec.ts («slå fra → slet data»)

## Forslag
Enten sletter `delete_data` også de opgaver, appen har oprettet (task_id i appdata – og tilbagekalder evt. delte links), eller teksten siger ærligt, at listen bliver i Opgaver. Det første matcher løftet «alt».

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
