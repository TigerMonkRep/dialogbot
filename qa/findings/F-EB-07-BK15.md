---
id: F-EB-07-BK15
scenario: BK15
reported_by: e2e-erhverv (B)
severity: S2
status: fixed
owner_fix: fix-engineer
related: [W13]
---

## Kort
/app/aftaler lover «Flyt eller aflys her», men aftalekortet har kun «Aflys» – der findes ingen måde at flytte en aftale i UI'et (kun assistentens flyt_tid).

## Trin til at genskabe
1. Opret en booking. 2. /app/aftaler?uge=<dag> → klik aftalen.

## Forventet
Teksten svarer til funktionen (fjern «Flyt» eller byg flyt). Backend har `bookings.service.move`, men intet endpoint.

## Faktisk
Kun knapperne Ring/Henvendelse/Aflys.

## Evidens
- qa/evidence/BK15/*-aftalekort.png
- Test: web/e2e/qa/erhverv-b/BK06.spec.ts («lover Flyt eller aflys her»)

## Rodårsag (gæt)
web/src/i18n/messages/da/app.json:337 (bookings.intro) vs. web/src/app/app/(admin)/aftaler/client.tsx BookingCard; app/modules/bookings/router.py mangler et move-endpoint.

## Rodårsag
`bookings.intro` lovede «Flyt eller aflys her», men UI'et har kun «Aflys» (intet move-endpoint; flyt findes kun som assistentens `flyt_tid`).

## Rettelse (filer)
- `web/src/i18n/messages/{da,en,de,es,fr,it,no,sv}/app.json` `bookings.intro`: «Aflys her. …» (og tilsvarende). Flyt-funktion er ikke bygget (efter instruks).
- Commit: (lead committer)

## Testresultat
- i18n:check ok. E2E `web/e2e/qa/erhverv-b/BK06.spec.ts` («lover Flyt eller aflys her») kræver rebuild – verifier.
