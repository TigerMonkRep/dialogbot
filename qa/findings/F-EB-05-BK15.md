---
id: F-EB-05-BK15
scenario: BK15
reported_by: e2e-erhverv (B)
severity: S1
status: closed
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
- Commit: (lead committer) – beslutningsdel: se «Beslutning»

## (afgjort 2026-11-10 – se «Beslutning») needs-decision: `connected_busy` returnerer [] ved udbyderfejl
`connectors/calendar.py connected_busy` registrerer fejlen på forbindelsen og returnerer `[]`, så ledige tider beregnes alene ud fra åbningstider – assistenten/widgetten kan booke oven i ejerens optagede Google-tid under et nedbrud. Ikke ændret (produktbeslutning). Muligheder:
1. **Fail-closed:** ved fejl tilbydes ingen online-tider (assistenten tilbyder at en medarbejder ringer tilbage). Ingen dobbeltbookinger, men tabt booking under nedbrud.
2. **Fail-open med sidst kendte optaget tid (nuværende + forbedring):** brug sidst hentede optagne perioder (cache) og/eller kun åbningstider, men markér bookinger lavet under fejl som «afventer bekræftelse» over for kunden og ejeren. Flere bookinger, risiko for konflikt som en medarbejder må løse.

## Beslutning
- Dato: 2026-11-10 kl. 17:26 (Fürster). Valgt: anbefalingen = mulighed 2, fail-open med «afventer bekræftelse».
- Rodårsag (connected_busy): udbyderfejl returnerede `[]` uden at nogen fik det at vide, og en forbindelse der allerede stod i `error` blev sprunget over (så faldt man tavst tilbage til iCal/åbningstider).
- Rettelse:
  - Migration `alembic/versions/e7a2c5d9f1b3_booking_confirmation.py` (ny, reversibel, additiv): `bookings.confirmation` NULL | 'pending' | 'confirmed' (+ check-constraint). `status` er uændret 'confirmed', så aftalen stadig blokerer tiden overalt (slots, SMS, rapporter). upgrade → downgrade -1 → upgrade testet på qa_fix; `alembic check`: "No new upgrade operations detected".
  - `connectors/calendar.py connected_busy` → `(busy, readable)`; forsøger også forbindelser i `error` og sætter dem `connected` igen, når læsningen virker (kun hvis fejlen var en læsefejl). `mirror_create` springer aftaler i 'pending' over (de skrives ved bekræftelse).
  - `bookings/service.py`: `slots_state`/`_busy_state`; `book()` og `move()` sætter `confirmation='pending'`, når optaget tid ikke kunne læses, opretter opgaven «Bekræft aftale: …» (Opgaver) og sender push til arbejdsrummet (`push.notify_workspace`). `confirm()` viser konflikt med optaget tid ærligt (409 `calendar_conflict` med perioderne) medmindre `override_conflict`; afslutter opgaven. Aflysning afslutter også opgaven. `booking_out` + webhook-payload får `confirmation`.
  - `bookings/router.py`: `POST /workspaces/{ws}/bookings/{id}/confirm` (bookings.create) → spejler via `mirror_create`/`mirror_update` (fejl → «Ikke i kalenderen» som før), audit `bookings.confirmed`; `calendar_connection.pending_confirmation`; widget-svar `confirmation`.
  - Assistent: `book_tid`/`flyt_tid` returnerer `bekraeftelse: "afventer"` og teksten «Tiden … er noteret, men den er IKKE endeligt bekræftet … en medarbejder vender tilbage og bekræfter tiden …» (ingen «Booket»/«er flyttet»); `ledige_tider` siger, at en valgt tid skal bekræftes. Sælger-Peters `book_moede` (sales/tools.py) siger tilsvarende «noteret, ikke endeligt bekræftet». SMS-skabelonen «booking» afvises for en aftale, der afventer (`booking_pending`).
  - Widget (`webchat/static/frame.js`, kun dansk som resten af widgetten): «Tak, X! Din tid … er noteret. En medarbejder bekræfter tiden.»
  - Web /app/aftaler: mærkat «Afventer bekræftelse», forklaring, knap «Bekræft» (→ «Bekræft alligevel» ved konflikt), antal i kalenderkortet, «Book for en kunde» viser «Noteret … – afventer bekræftelse». i18n i 8 sprog (`bookings.card.pending|pendingDetail|confirm|confirming|confirmAnyway`, `bookings.calendar.pendingN`, `bookings.book.pending`).
  - Test-hook (kun dev/fake): `POST /dev/fake-calendar/busy-down?workspace_id=…&down=…` (fakes `WORLD.busy_down`, pr. arbejdsrum).
- Tests: `tests/test_booking_calendar_sync.py` (6 nye: udbyder nede → afventer + opgave + intet event, bekræft → spejlet + opgave lukket; konflikt 409 + bekræft alligevel; aflys lukker opgave; kalender ok → normal; book_tid/flyt_tid giver aldrig «Booket»/«er flyttet»; forbindelse i error forsøges og gendannes), `tests/qa/test_qa_voice_calendar_failure.py::test_bk15_busy_unreadable_booking_is_noted_not_confirmed` + eval-case `qa/voice/cases/BK15-03`, e2e `web/e2e/qa/erhverv-b/BK15-pending.spec.ts` (desktop + mobil).
- Ikke ændret (opfølgning): public API v1 `Booking`-skemaet viser ikke `confirmation` (versioneret kontrakt); `SalesMeeting.status` for et afventende sælgermøde er stadig 'confirmed'; webchat-indbakkens «Booket»-udfald skelner ikke afventende aftaler.

## Testresultat
- Før: `test_bk15_failed_external_move_is_not_reported_as_done`, `test_bk15_failed_external_create_is_not_reported_as_done` FAILED.
- Efter: pass (se F-EB-04-W12 for samlet kørsel).

## Verifikation (udfyldes af verifier)
- Gentest: pass på c3bed12 (db qa_verify_b og qa_verify): test_qa_w12_bk15.py::test_bk15_failed_external_move/create_is_not_reported_as_done, test_qa_voice_calendar_failure.py (2/2), test_qa_integ_E07.py (rettet af verifier: book_tid med fejlende kalender er nu `failed`, booking står med calendar_sync='failed')
- Fejler testen uden rettelsen? ja – worktree 56f95ab (/home/claude/wt-before), db qa_verify_before: `action status='ok', text to caller='Aftalen er flyttet til tirsdag 10. november kl. 18.00. (simuleret)'; Dialogbot=…17:00, Google=…14:00`; `Peter is handed 'Booket: Besigtigelse …'`; E07-testen: `assert 'ok' == 'failed'`
- Naboscenarier kørt: hele tests/qa + fuld `pytest` fra ren db qa_verify på c3bed12 (1610 passed, 18 xfailed, 5 skipped m. grund, 1 failed = F-VR-03, urelateret race); E07-inventar, test_booking_calendar_sync.py.
- Dom: closed
