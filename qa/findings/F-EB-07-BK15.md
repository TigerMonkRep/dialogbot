---
id: F-EB-07-BK15
scenario: BK15
reported_by: e2e-erhverv (B)
severity: S2
status: closed
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

## Verifikation (udfyldes af verifier)
- Gentest: pass 2/2 (run2–3; testen er ny efter run1) desktop-1440 + mobil-390: web/e2e/qa/erhverv-b/BK06.spec.ts «lover kun «Flyt», hvis en aftale kan flyttes» (testen omskrevet af verifier: den gamle asserterede både løftet «Flyt eller aflys her» og en Flyt-knap; rettelsen fjernede løftet, så nu testes ærlighed: intet Flyt-løfte uden Flyt-knap. Selve flyt-funktionen er en separat test.fail «BK15 move appointment in /app/aftaler: not-implemented»)
- Fejler testen uden rettelsen? ja – pre-fix frontend (56f95ab bygget i /home/claude/wt-before, next start :3500 mod API :8000), /home/claude/verify-logs/e2e_before.log: begge: `promises «Flyt» (1) without a move button (0)`
- Naboscenarier kørt: e2e P0-suite (web/e2e/qa uden privat) mod frisk Next-build af c3bed12 på :3300 (se note: :3000 kører stadig den gamle build), run2 102/102 og run3 102/102 (run1 98/100: kun den gamle BK06-«Flyt»-test, siden rettet); journeys.spec.ts 64: 61+3 fejl, alle forklaret (rapport); 
- Dom: closed
