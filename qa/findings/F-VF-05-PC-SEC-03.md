---
id: F-VF-05-PC-SEC-03
scenario: PC-SEC-03
reported_by: verifier
severity: S3
status: new
owner_fix: ui-ux-engineer
related: [F-PS-07-PC-SEC-03, F-PK-03-PC-SEC-03]
---

## Kort
Når Privat-API'et svarer 403 privat_not_enabled, viser Min dag (og Opgaver uden indhold) ingen besked, før brugeren har sendt noget; først da kommer «Dialogbot Privat er ikke slået til». Ingen simulering og ingen falske tal (selve S1-fundet er lukket). web/e2e/qa/privat-deep/core/sikkerhed.spec.ts er stadig rød 2/2 i begge viewports på /privat/dag og /privat/butik (Butikkens «Apps kan ikke hentes lige nu» matcher ikke testens regex).

## Forventet
Fejlbanneret (errors.notEnabled) vises ved indlæsning på alle Privat-skærme – eller testen tilpasses, hvis qa-lead accepterer «fejl ved første handling».
Screenshots: /home/claude/verifier-final/shots/sec03-*.png
