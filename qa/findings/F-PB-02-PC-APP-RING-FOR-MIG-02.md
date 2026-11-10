---
id: F-PB-02-PC-APP-RING-FOR-MIG-02
scenario: PC-APP-RING-FOR-MIG-02
reported_by: e2e-privat (PB)
severity: S2
status: new
owner_fix: fix-engineer
related: [PC-APP-RING-FOR-MIG-01, F-UX-01]
---

## Kort
«Ring for mig» er med i alle planer (Basis, Plus og Familie), men en bruger uden plan får at vide, at den er «med i Plus og Familie». Det sker både i API-fejlen og i plan-arket, og det leder brugeren mod en dyrere plan, end der er brug for.

## Trin til at genskabe
1. Ny konto uden plan (ingen prøveperiode).
2. `POST /privat/addons/ring-for-mig/enable` → 409 `needs_plan`, `plans: ["basis","plus","familie"]`, message «Ring for mig er med i Plus og Familie – start 14 dage gratis eller vælg en plan».
3. Browser: Butikken → Ring for mig → «Prøv gratis» → PlanSheet: brødteksten `apps.planTextTrial` siger «Ring for mig er med i Plus og Familie …», mens radiogruppen viser Basis, Plus og Familie.

## Forventet
Kataloget (addons.py:114 `included_in=("basis","plus","familie")`, `price_text` «Med i alle planer») og badget «Med i alle planer».

## Faktisk
`addons.enable()` vælger `names[:2]` af («Plus», «Familie», «Basis») og dropper derfor Basis. `apps.planTextTrial`/`planTextEnded` er hårdkodet til «Plus og Familie» for alle apps.

## Evidens
- Test: tests/qa/test_qa_pd_apps_b.py::test_01_needs_plan_message_for_ring_for_mig_names_basis (fejler i dag)
- Browser: web/e2e/qa/privat-deep/apps-b/ring-for-mig.spec.ts («02 …uden plan»), screenshots qa/evidence/PC-APP-RING-FOR-MIG-02/

## Forslag
Teksten skal bygges ud fra `included_in`: «med i alle planer», når basis er med, og ellers «med i Plus og Familie».

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
