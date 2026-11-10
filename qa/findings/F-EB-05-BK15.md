---
id: F-EB-05-BK15
scenario: BK15
reported_by: e2e-erhverv (B)
severity: S1
status: fixed
owner_fix: fix-engineer
related: [DB-007, DB-011, W13]
---

## Kort
Når kalenderudbyderen fejler ved flyt/oprettelse, får kunden alligevel «Aftalen er flyttet til …» / «Booket …», handlingsloggen siger ok, og der findes ingen genforsøg eller afstemning – Dialogbot og Google viser to forskellige tider.

## Trin til at genskabe
1. Google forbundet; assistenten booker (book_tid) → event i Google.
2. Google fejler update_event; assistenten kører flyt_tid til en ny tid.

## Forventet
DB-007: "no blind new write after timeout"; DB-011: "unknown move cannot promise old external event unchanged … show last confirmed time while unknown; safe conditional retry".

## Faktisk
ActionRun.status=ok, tekst til kunden: "Aftalen er flyttet til tirsdag 10. november kl. 15.00. (simuleret)". Dialogbot: 14:00Z, Google: stadig 11:00Z. Kun forbindelsen markeres `error`. Samme for create: booking bekræftet, intet event, intet genforsøg.
Relateret: `connected_busy` returnerer [] ved udbyderfejl (calendar.py:370) → ledige tider beregnes kun ud fra åbningstider, så assistenten kan booke oven i ejerens optagede Google-tid under et nedbrud (kræver produktbeslutning).

## Evidens
- qa/evidence/BK15/pytest-erhverv-b.log
- Tests: tests/qa/test_qa_w12_bk15.py::test_bk15_failed_external_move_is_not_reported_as_done, ::test_bk15_failed_external_create_is_not_reported_as_done

## Rodårsag (gæt)
app/modules/integrations/connectors/calendar.py:304-311 – `_mirror_update`/`_mirror_create` (linje 322-346) sluger ActionError via `_note` og returnerer altid ok-resultat. Ingen vedvarende operation-identitet til afstemning.

## Rodårsag
`CalendarActions._mirror_create/_mirror_update/_mirror_delete` slugte `ActionError` (kun `_note` på forbindelsen) og `run()` returnerede altid et ok-`ActionResult` med «Booket …»/«Aftalen er flyttet til …». `actions.execute` satte derfor `ActionRun.status='ok'`, og kalderen fik en løgn.

## Rettelse (filer)
- Migration `alembic/versions/b4d8e2f6a1c3_booking_calendar_sync.py` (ny, reversibel, additiv): `bookings.calendar_sync` (NULL | 'synced' | 'failed', check-constraint) + `bookings.calendar_sync_error`. Testet `upgrade head` → `downgrade -1` → `upgrade head`; `alembic check`: "No new upgrade operations detected". Model: `app/models/domain.py` `Booking`.
- `app/modules/integrations/connectors/calendar.py`: én fælles spejlingssti `mirror_create` / `mirror_update` / `mirror_cancel` (+ `connected_calendar`). Ved fejl: `calendar_sync='failed'` + fejltekst på bookingen og forbindelsen sættes i `error`. Bruges af `CalendarActions` (assistent) og af routerne. Forbindelser i `error` forsøges stadig (og flagges ved fejl) i stedet for at blive sprunget tavst over; den indbyggede kalender (når Google-forbindelsen står i error og derfor ikke leverer værktøjer) spejler også.
- `app/modules/bookings/router.py`: `manual_booking` («Book for en kunde») og `visitor_book` (widget) kalder `mirror_create`; `cancel` kalder `mirror_cancel` (manuel aflysning slettede heller ikke eventet – samme rodårsag).
- `app/modules/bookings/service.py` `booking_out`: `calendar_sync`, `calendar_sync_error`.
- Web: `aftaler/types.ts`, `aftaler/client.tsx` BookingCard viser mærkat «Ikke i kalenderen» + fejldetalje; `aftaler/page.tsx` viser antal sync-fejl. i18n `bookings.card.syncFailed|syncFailedDetail` i 8 sprog.
- Ny test: `tests/test_booking_calendar_sync.py` (ingen kalender → intet spejl; manuel booking + aflysning spejles; fejlet spejl flagges synligt og forbindelsen i error).
- `book_tid`: fejler spejlingen, står aftalen i Dialogbot med `calendar_sync='failed'`, og handlingen kaster `ActionError(code='calendar_sync_failed')` → `ActionRun.status='failed'`, ingen `action.completed`-webhook, og assistenten får: «Handlingen fejlede: Tiden … er noteret hos virksomheden, men kunne ikke skrives i virksomhedens kalender (…). Lov ikke kunden, at tiden er bekræftet – sig at en medarbejder bekræfter tiden. Sig det ærligt …».
- `flyt_tid`: samme; teksten lover ikke den nye tid. Bookingen står på den nye tid i Dialogbot med `calendar_sync='failed'` (synlig for ejeren), Google beholder den gamle – uoverensstemmelsen er nu markeret i stedet for skjult. (Rollback til den gamle tid blev fravalgt, fordi en timeout kan have flyttet eventet alligevel; reporterens test forudsætter også, at Dialogbot står på den nye tid.) En senere flytning prøver igen; mangler eventet helt, oprettes det.
- `aflys_tid`: aflysningen står (kunden har aflyst); fejler sletning i kalenderen, flagges bookingen `failed`, så ejeren ser, at eventet stadig ligger i kalenderen.
- `ActionRun.status` bruger eksisterende `failed` (check-constraint ok/failed/refused) – ingen ny «afventer»-status, for at undgå endnu en migration; fejlteksten beskriver, at tiden er noteret og afventer bekræftelse.
- Commit: (lead committer)

## needs-decision: `connected_busy` returnerer [] ved udbyderfejl
`connectors/calendar.py connected_busy` registrerer fejlen på forbindelsen og returnerer `[]`, så ledige tider beregnes alene ud fra åbningstider – assistenten/widgetten kan booke oven i ejerens optagede Google-tid under et nedbrud. Ikke ændret (produktbeslutning). Muligheder:
1. **Fail-closed:** ved fejl tilbydes ingen online-tider (assistenten tilbyder at en medarbejder ringer tilbage). Ingen dobbeltbookinger, men tabt booking under nedbrud.
2. **Fail-open med sidst kendte optaget tid (nuværende + forbedring):** brug sidst hentede optagne perioder (cache) og/eller kun åbningstider, men markér bookinger lavet under fejl som «afventer bekræftelse» over for kunden og ejeren. Flere bookinger, risiko for konflikt som en medarbejder må løse.

## Testresultat
- Før: `test_bk15_failed_external_move_is_not_reported_as_done`, `test_bk15_failed_external_create_is_not_reported_as_done` FAILED.
- Efter: pass (se F-EB-04-W12 for samlet kørsel).
