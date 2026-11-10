---
id: F-EB-06-BK15
scenario: BK15
reported_by: e2e-erhverv (B)
severity: S2
status: fixed
owner_fix: fix-engineer
related: [BK06]
---

## Kort
/app/aftaler viser «Kalender: Ikke forbundet – Uden kalender kender Dialogbot kun åbningstiderne …», selv om Google Kalender er forbundet (og bruges som kilde til optaget tid).

## Trin til at genskabe
1. Ny ejer, online booking slået til. 2. Forbind Google Kalender (Indstillinger → Integrationer). 3. Åbn /app/aftaler.

## Forventet
UI fortæller sandheden om kalenderstatus (README: "UI lyver" er mindst S1/S2; brief: ærlig integrationsstatus).

## Faktisk
Kortet viser "Ikke forbundet" + "Uden kalender…" (desktop og mobil), mens /integrations giver google_calendar.status=connected.

## Evidens
- qa/evidence/BK15/*-aftaler-kalenderkort.png, qa/evidence/BK15/pw/*Ikke-forbundet*/
- Test: web/e2e/qa/erhverv-b/BK06.spec.ts («kalenderkortet viser den forbundne Google-kalender»)

## Rodårsag (gæt)
web/src/app/app/(admin)/aftaler/page.tsx:85-88 ser kun på `s.busy_ics_url`; OAuth-forbindelser (integrations) indgår ikke i bookings/settings-svaret.

## Rodårsag
`/app/aftaler`-kortet (`web/src/app/app/(admin)/aftaler/page.tsx`) så kun på `bookings/settings.busy_ics_url`; svaret indeholdt intet om OAuth-forbindelser (Google/Microsoft), så en forbundet kalender blev vist som «Ikke forbundet».

## Rettelse (filer)
- `app/modules/bookings/router.py`: `settings_out` returnerer `calendar_connection` = `{connector, status, error, simulated, last_ok_at, sync_failed}` for den forbundne Google/Microsoft-kalender (også simuleret), ellers `null`. Kilde: `connectors/calendar.py connected_calendar()` (samme som spejlingen bruger).
- `web/src/app/app/(admin)/aftaler/types.ts`, `page.tsx`: kortet viser «Forbundet» + «Google Kalender (simuleret) er forbundet. Nye aftaler skrives i kalenderen …», «Kunne ikke læse kalenderen» + fejltekst ved `status=error`, og antal aftaler med sync-fejl. iCal-visningen bruges uændret, når ingen OAuth-kalender er forbundet.
- Nye i18n-nøgler i alle 8 sprog: `bookings.calendar.linked|linkedError|syncFailedN|simulated|provider.google_calendar|provider.microsoft_calendar`.
- Test: `tests/test_booking_calendar_sync.py` (calendar_connection null/forbundet/fejl).
- Commit: (lead committer)

## Testresultat
- Backend pass; tsc + i18n:check ok. E2E `web/e2e/qa/erhverv-b/BK06.spec.ts` («kalenderkortet viser den forbundne Google-kalender») kræver rebuild – verifier.
