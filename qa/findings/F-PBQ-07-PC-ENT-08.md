---
id: F-PBQ-07-PC-ENT-08
scenario: PC-ENT-08
reported_by: billing-qa
severity: S1
status: confirmed
owner_fix: fix-engineer
related: []
---

## Kort
Familie (169 kr./md. eller 1.620 kr./år) sælges med «Op til 5 personer», men der findes ingen måde at give 4 andre adgang til planen. `people_limit` er kun et tal i API-svaret.

## Trin til at genskabe
1. Konto med Familie (aktiv).
2. `GET /privat/subscription` → `people_limit: 5`, og Familie-features har «Op til 5 personer».
3. Søg i OpenAPI (104 /privat-stier) efter household/husstand/family/plan-members: ingen.
4. `people_limit` bruges i app/modules/privat kun i `entitlements()` (subscriptions.py ~158) og læses ingen andre steder. Ingen model knytter brugere til en plan.

## Forventet
Hvad der sælges, findes: 4 husstandsmedlemmer kan få Familiens rettigheder (opkald fra fælles kvote, apps), eller også fjernes løftet fra plankortene.

## Faktisk
UI lover det på plankort, PlanSheet og landing:
- `plan.people`/`landing.pricing.features.people`: «Op til # personer»
- `apps.planFacts`: «… · op til # personer»
- `FEATURES["familie"]`: «Op til 5 personer»

Forskellen på Plus og Familie er derfor kun 15 opkald mere for 70 kr./md. mere. Det er også en mulig markedsføringsrisiko: et betalt løfte, der ikke leveres.

## Evidens
- Test: tests/qa/test_qa_pd_billing.py::test_pc_ent_08_familie_people_limit_has_no_way_to_add_people (fejler: «no household/family endpoint among 104 /privat routes; people_limit used only as …»)

## Beslutning nødvendig
Det er en produktbeslutning for Fürster, om husstandsdeling skal bygges nu, eller om «Op til 5 personer» skal fjernes eller markeres som «kommer snart». Indtil da bør fix-engineer/ui-ux-engineer fjerne eller markere løftet.

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
