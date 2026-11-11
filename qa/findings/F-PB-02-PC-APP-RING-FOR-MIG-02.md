---
id: F-PB-02-PC-APP-RING-FOR-MIG-02
scenario: PC-APP-RING-FOR-MIG-02
reported_by: e2e-privat (PB)
severity: S2
status: reopened
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
- Rettelse: needs_plan-beskeden siger «alle planer», når appen er med i Basis, Plus og Familie (addons.enable). Til en kunde med rettigheder lyder den «skift plan under Konto» (F-UX-01).
- Filer: app/modules/privat/addons.py
- Test: tests/qa/test_qa_pd_apps_b.py::test_01_needs_plan_message_for_ring_for_mig_names_basis (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: API rettet («med i alle planer»), men plan-arket for en bruger uden plan har stadig overskriften «Ring for mig kræver Plus» og eyebrow «MED I PLUS OG FAMILIE» over brødteksten «Ring for mig er med i alle planer» (privat.json apps.planTitle «{name} kræver Plus», apps.planEyebrow «Med i Plus og Familie» – hårdkodet for alle apps). Screenshot /home/claude/verifier-final/shots/gate-05-slaa-til.png. Desuden siger chatkortet «Ring for mig er ikke slået til – Slå til» i stedet for «Kræver en plan»
- Fejler testen uden rettelsen? -
- Naboscenarier kørt: PREVIEW_GATE=on :3401, gæst uden plan
- Dom: reopened
