---
id: F-PX-09-PC-DAY-04
scenario: PC-DAY-04
reported_by: i18n-a11y-qa (PX)
severity: S3
status: new
owner_fix: ui-ux-engineer
related: []
---

## Kort
Desktop (1280×800) /privat/dag: efter «Enter» i samtale-feltet står fokus på `<body>` – brugeren skal klikke i feltet igen for næste besked (tastatur/skærmlæser mister placering).

## Forventet
PC-DAY-04: «fokus bliver i inputfeltet efter send».

## Faktisk
`document.activeElement.tagName === "BODY"` 1,5 s efter send (2 kørsler, også på 451d53b).

## Evidens
- web/e2e/qa/privat-deep/x/a11y-pwa.spec.ts «PC-SHOP-12/PC-DAY-04», qa/evidence/PX/day04-desktop.json
