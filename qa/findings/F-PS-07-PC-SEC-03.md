---
id: F-PS-07-PC-SEC-03
scenario: PC-SEC-03
reported_by: security-privacy
severity: S1
status: new
owner_fix: fix-engineer
related: [e2e-privat (PC-SEC-03 ejer – dedupe hvis de også indberetter), ui-ux-engineer]
---

## Kort
En indlogget bruger, som ikke er på Privat-pilotlisten (eller får 404 fra API'et), sendes stille ind i in-browser-simuleringen: lister, deling, «opkald» og «betaling» ser rigtige ud, og på mobil er headerens «Simuleret»-mærke skjult.

## Trin til at genskabe
1. Backend med `PRIVAT_ALLOWED_EMAILS=<andre>` (lukket pilot – prod-konfigurationen indtil åbning).
2. Log ind som bruger uden for listen, åbn /privat på 390 px.
3. `POST /privat/account` → 403 `privat_not_enabled` → web/src/components/privat/store.tsx:163 `if (isUnavailable(e)) { m = useFake(FAKE_KEY, "fake"); }` (api.ts `isUnavailable` = 404 | privat_not_enabled | feature_disabled | privat_disabled).
4. Header: shell.tsx:124 `{simulated && <span className="hidden sm:inline-flex"><Sim /></span>}` – usynlig under 640 px.

## Forventet
PC-SEC-03: «Brugeren må ikke tro at handlinger (opkald, betaling, invitationer) er udført; «Simuleret»-mærke synligt overalt.» En indlogget bruger, der ikke har adgang, skal have en tydelig «Du er ikke med i piloten endnu»-tilstand – ikke en simulering af sine egne data. Et 404 fra API'et (deploy-fejl) må ikke ligne succes.

## Faktisk
Simuleringen startes uden besked; kun enkelte kort (opkald, konto-siden) bærer «Simuleret»-pille. Delte links fra simuleringen peger på invitationer, der ikke findes. Fake-data gemmes i sessionStorage (se F-PS-09).

## Evidens
- Test (kildekontrol): tests/qa/test_qa_pd_sec.py::test_ps_sim_01_logged_in_user_never_silently_falls_back_to_the_simulation
- Backend-halvdelen: app/modules/privat/deps.py:43-50 (`privat_not_enabled` for e-mails uden for listen).

## Rodårsag (forslag)
store.tsx: for `session.loggedIn` brug ALDRIG fake; vis en fejl-/venteliste-tilstand ved `privat_not_enabled`, og en almindelig fejl ved 404. Behold fake kun for `FORCE_FAKE` og anonyme demo-besøg. Gør header-mærket synligt på mobil, når simulering er aktiv.

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
