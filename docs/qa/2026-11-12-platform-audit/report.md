# Platform-audit Dialogbot – gen-audit 13/11-2026 (verifier)

**FORELØBIG LANCERINGSBESLUTNING: NO-GO** (uændret fra 12/11, men med færre blokkere, se nedenfor)

- **Gate-kandidat:** `ad35825` (PR #224, base main 4c1ac89 = #217/#218/#219/#221). Træet er identisk med main-merge
  `5aaa7e2` (`git diff ad35825 5aaa7e2` er tom). Alembic har ét head `f1b3d5a7c9e2`. main 4c1ac89 alene havde to
  heads og kunne ikke migreres (`Multiple head revisions`). Senere main (9c86382: outreach/billing) er ikke gatet
  lokalt. Featurekoden for H01/M06/M03/E07/W04/W09/W13 er uændret mellem 142e380 og 9c86382.
- **Feature-verifikation:** main `142e380` (#213, #214, #215), uafhængigt af bygherrerne (separat verifier-agent).
- **Miljø:** lokal stak (PostgreSQL 16, API :8336, worker, Next production build :3336) med fake-udbydere og CI-env fra
  `.github/workflows/e2e.yml`. Ren database pr. kørsel og ren browserprofil pr. test (Playwright-kontekst,
  `workers: 1`, `retries: 0`). Maskinen (2 CPU) var delt med andre agenters stakke, med load op til 19.

## Resultater på gate-kandidaten (ad35825), begge viewports 1440 + 390
| Kontrol | Lokalt | CI (push-run 43428208331 / 43428208100) |
|---|---|---|
| ruff, alembic upgrade (ren DB) + check + heads, tsc, i18n:check, next build | exit 0, ét head | grøn |
| pytest (CI-env, ren DB) | 2664: **2586 bestået, 0 fejl**, 39 skip, 39 xfail | 2585 bestået, 0 fejl, 40 skip, 39 xfail |
| Journeys (deploy-gaten) | 378: 222 bestået, **1 fejl (flaky)**, 155 skip | 225 bestået, 0 fejl, 153 skip |
| QA-katalog e2e/qa (uden pwa) | 892: 586 bestået (heraf **122 forventede fejl** `test.fail` = kendte defekter/ikke bygget), 0 fejl, 306 skip | 584 bestået, 308 skip (4 shards) |
| QA-katalog pwa | 10 bestået | 10 bestået |
| privat-job (fake mode) | ikke kørt lokalt | 92 bestået, 2 skip |

Skip, xfail og `test.fail` tæller ikke som PASS. 306+155 skip er primært privat-deep-specs, der kræver
qa_privat_stack, og som heller ikke kører i CI (F-AUD26-03).

**Flaky (< 3/3):**
- `e2e/erhverv/G-trin1-journey.spec.ts:162` «Trin 1 (e) rebotti.dk» [desktop]: timeout på klik på
  `<summary>` i gate-kørslen. Bagefter 3/3 grøn (30/30 med hele filen ×3, begge viewports).
- `e2e/qa/i18n/x24-locales.spec.ts:200` axe [mobil-390]: fejlede i 142e380-katalogkørslen (`da /: color-contrast` 3,16:1,
  `#848d9e` på `#f6f9fd`, `.entry-module__…b1`). Bagefter 6/6 grøn med ×3, og grøn i gate-kørslen. Testen springes
  over i CI (axe er ikke installeret). Kontrasten bør tjekkes manuelt (mulig animation/overgang).
- `W13.spec.ts:30` [mobil-390] med `--repeat-each=3`: 1/3, fordi den 2. og 3. gentagelse fik 429 `sms_rate_limited`
  (to 429 på `/booking/manage/***/code` i API-loggen). Det er grænsen på 5 koder pr. IP pr. time, og alle
  gentagelser kommer fra 127.0.0.1. Produktet gør det rigtige, men specen kan ikke gentages > 2× i timen fra én IP.
  Desktop 3/3. I gate-kataloget og CI er den grøn.

## Uafhængig verifikation af H01, M06, M03, E07, W04, W09, W13 (main 142e380)
Metode: (1) Produktkoden fjernes (`app/` ved PR-base), og testene beholdes. Så fejler alle fire grupper (rc 1/2), og
med koden består 55/55 (`qa/evidence/VER1113/coarse-revert.txt`). (2) 36 målrettede mutationer af de egenskaber,
opgaven nævner: 31 dræbt, 5 overlever (`qa/evidence/VER1113/mutations.txt`). (3) Prober for fejlklasser
(`qa/evidence/VER1113/test_ver1113_probes.py`). (4) E2E-specs ×3 begge viewports: 100/102, se flaky ovenfor.

| Scenarie | Egenskab | Bevis | Dom |
|---|---|---|---|
| H01 | tenant-isolation, rolle-matrix (læser ser ikke sager), interne noter og deres vedhæftninger aldrig hos kunden | 5/5 mutationer dræbt | **PASS** |
| M06 | kun operatører, intern note vs. kundesvar | 1 dræbt, 1 overlever: intern note der mailer kunden fanges ikke (F-VER1113-03, S3 testhul; koden er korrekt) | **PASS** |
| M03 | genkørsel = præcis ét forsøg, aldrig `done`, idempotent (Idempotency-Key), ingen blind kalenderskrivning efter timeout, suspendering stopper worker/dialler/actions kun for den kunde, kun operatør | 9/9 dræbt | **PASS** |
| E07 | 8 varianter × 8 sprog, preview sender intet, tenant-afgrænset booking_id, e-mail i `sandbox`-iframe | 2/2 dræbt | **FAIL (pass-delvist)**: automatisk afsendelse mangler (beslutning i åben PR #222) |
| W04 | kode kræves, 5 forsøg, udløb, bundet til samtale/nummer, cooldown, kun frame-origin; widget uden innerHTML på nye data (kun `textContent`/DOM, `manageLink` kun http(s)) | 6 dræbt; IP-/virksomhedsgrænse overlever, men virker (prober: 429 ved 6. kode/IP og 61. kode/virksomhed) → F-VER1113-05 (S3) | **PASS** |
| W09 | 404 ukendt/erstattet/andet formål, 410 udløbet, HMAC med formål, ingen noter i visning, kundens fravalg fjerner ikke personalets | dræbt; HMAC→SHA overlever (ikke black-box-observerbar, læst i koden); formål fjernet fra HMAC overlever (3. lag: objekt-opslag giver 404) | **FAIL**: token logges i klartekst (F-VER1113-06, S1) |
| W13 | kode før ændring, session bundet til linket, frist, kalenderfejl → `pending` | dræbt | **FAIL**: dobbelt kalender-DELETE (F-VER1113-01, S2), linket dør efter flytning (F-VER1113-02, S2), token i log (F-VER1113-06) |

## Nye fund (qa/findings/F-VER1113-*)
| ID | Alvor | Status | Kort |
|---|---|---|---|
| F-VER1113-06-W09 | S1 | new | `/public/customer/callback/<token>` og `/public/booking/manage/<token>` mangler i `_SECRET_PATHS` → bearer-token i API-loggen (samme klasse som F-PS-04, S0) |
| F-VER1113-01-W13 | S2 | new | Aflysning (kunde via link og personale) sender DELETE til kalenderen 2×. Med Googles 410 bliver aftalen `calendar_sync=failed`, og forbindelsen går i fejl |
| F-VER1113-02-W13 | S2 | new | Linket udløber ved den oprindelige sluttid efter flytning til senere dag → 410 |
| F-VER1113-03-M06 | S3 | new | Testhul: intern note → kundemail fanges ikke |
| F-VER1113-04-W04 | S3 | needs-decision | Webchat-booking gemmer telefonnummer uden SMS-kode (W04 dækker kun «Bliv kontaktet») |
| F-VER1113-05-W04 | S3 | new | Testhul: IP-/virksomhedsgrænser for SMS-koder |

Rodårsag, trin og evidens står i hver fundfil. Den stale docstring i `tests/qa/test_qa_integ_E07.py` («xfail(strict):
E07 is not implemented») er kun nævnt her.

## Status i registret efter gen-audit (traceability.csv, genereret)
| | P0 PASS/FAIL/ikke testet/BLOCKED | P1 PASS/FAIL/ikke testet/BLOCKED |
|---|---|---|
| Erhverv (12/11) | 13 / 18 / 6 / 1 | 1 / 4 / 83 / 0 |
| **Erhverv (13/11)** | **17 / 14 / 6 / 1** | **1 / 4 / 83 / 0** |
| Privat (uændret) | 53 / 12 / 14 / 0 | 92 / 19 / 46 / 8 |

Ændret af verifier: M03 fix-ready→pass, H01/M06/W04 bekræftet pass, E07 fix-ready→pass-delvist, W09/W13
pass→fail (bygherren havde sat pass før verifikation). Erhverv P0, der ikke er PASS: A01, A05, A06, X09, W09, W13
(fail); R03, S02, M02, BK15, E07, X08, X20, X28 (pass-delvist); C09, C15, B03–B05, M04 (todo); X16 (blocked).

## Foreløbig GO/NO-GO: **NO-GO**
Begrundelse:
1. Åbne S0/S1-fund i registret, i alt 14: F-VER1113-06 (ny, S1) og 13 ældre. Af dem er 11 `fixed`/`fix-ready` og
   venter stadig på en verifier-dom (F-AUD26-02, F-HOT16-01, F-JE-02…05, F-FIX18-01, F-FIX20-01, F-FIX26-01,
   F-PBQ-06, F-VF-01), F-JE-01 er `new`, og F-PS-02 venter på en beslutning. De ligger uden for denne opgave, men
   blokerer stadig.
2. Erhverv P0: 14 FAIL og 6 ikke testet (C09/C15/B03–B05/M04 venter på scope-beslutning).
3. Kendte udestående, som ikke er mit ansvar: belastningstest og backup-restore (PR #220), manuel kalendertest,
   beslutninger i åbne PR'er (#223: SMS i baggrunden og widget på 8 sprog, hvor `frame.js` stadig har dansk hardkodet;
   #222: E07 auto-afsendelse), test i udbydernes sandkasser.

Det, der er blevet bedre siden 12/11: H01, M06, M03 og W04 er nu verificeret PASS. Kernegaten (pytest, journeys,
QA-katalog) er grøn på kandidaten bortset fra én flaky journey.

Genkørsel: `qa/evidence/VER1113/` (mutationsspec, prober, coarse-revert, logs). Lokale logs ligger i
`/home/claude/ver1113/logs/`.

---

# Historik: platform-audit 12/11-2026

**LAUNCH DECISION: NO-GO**

- **Produkt:** Dialogbot (dialogbot.app). Erhverv og Privat.
- **Scope:** Offentlig lancering. Udgående salgskontakt (cold outreach) findes, men er slået fra.
- **Kandidat:** c10d927271fc2d1c8e0c71a49daa1d23ab09f43a (origin/main 14edd47 + PR #206), med rent arbejdstræ.
- **Miljø:** Lokal stak med fake-udbydere (PostgreSQL 16, API, worker, Next production build) og GitHub Actions på PR-head. Mod produktion er der kun lavet læsende GET-kald.
- **Udført af:** qa-lead (audit) og hovedsessionen (koordinering).

## Kort resumé
Backend og brugerforløb er grønne. I pytest bestod 2410 tests og 0 fejlede. I journeys bestod 221 tests og 0 fejlede. Alle CI-jobs er grønne.

Lanceringen blokeres af:
- Et nyt S0-fund (F-AUD26-02): «Ring mig op nu» ringer til ethvert indtastet dansk nummer døgnet rundt uden bevis for, at nummeret tilhører den, der beder om opkaldet. Fürster har 12/11 valgt **A: SMS-kode først**, og rettelsen er under udvikling.
- I registret står 53 P0/P1-scenarier som FAIL, 149 som NOT TESTED og 9 som BLOCKED.
- Privat-dybdekataloget (cirka 420 specs) kører ikke i CI.
- Der mangler uafhængig verifikation, test mod udbydernes sandkasser, belastningstest og en øvelse i gendannelse fra backup.

## Ændringer i QA-agenterne
Ingen nye agenter. De ni ansvarsområder er fordelt på de eksisterende agenter. Seks agentfiler er opdateret:

| Agent | Ændring |
|---|---|
| i18n-a11y-qa | Travelpayouts Drive er fjernet efter #203. Et Travelpayouts-script på en Erhverv-side tæller nu som S1. Målet er WCAG 2.2 AA. |
| qa-lead | Regler for at starte agenter via Agent-værktøjet. Uden Agent-værktøj står uafhængig verifikation som BLOCKED. Audit-format, resultatord og tælling af skip. |
| verifier | Kandidat-SHA og primær evidens skal registreres. Skip, xfail og tests, der først består efter retry, tæller ikke som PASS. |
| api-contract-qa | Har nu også rollen som ydelses- og driftsreviewer. |
| security-privacy | OWASP ASVS 5.0 som reference. De nye offentlige indgange er med (demo-call, outreach, filimport). |
| voice-qa | Salgsopkald døgnet rundt. |

## Resultater
| Kontrol | Resultat |
|---|---|
| pytest (CI-miljø) | 2410 bestået, 0 fejl, 34 sprunget over, 49 xfail |
| ruff, alembic upgrade/check, tsc, i18n:check, next build | exit 0 |
| Journeys (deploy-gaten) | 221 bestået, 0 fejl, 123 sprunget over |
| CI på c10d927 | Alle jobs grønne (qa-catalog pr. shard: 215/1, 62+10/150, 215/1, 64/148 bestået/sprunget over) |
| Produktion (kun GET) | Migration som main. Ingen Travelpayouts-markører på Erhverv. 10×3 GET med 0,44–0,65 s i gennemsnit. |

### Status i registret
Skip, delvist bestået, ustabile og ikke-implementerede scenarier tæller ikke som PASS.

| | P0 PASS/FAIL/ikke testet/BLOCKED | P1 PASS/FAIL/ikke testet/BLOCKED |
|---|---|---|
| Erhverv | 13 / 18 / 6 / 1 | 1 / 4 / 83 / 0 |
| Privat | 53 / 12 / 14 / 0 | 92 / 19 / 46 / 8 |

P0-scenarier, der ikke er implementeret: H01, M03, M06, W04, W09, W13 og E07. C09, C15, B03–B05 og M04 står som «todo» efter skiftet til modellen med én plan.

## Fund i denne audit
| ID | Alvor | Status | Kort |
|---|---|---|---|
| F-AUD26-02-P06 | S0 | Beslutning A (SMS-kode), under rettelse | /demo-call ringer til ethvert nummer 24/7 uden bevis for ejerskab |
| F-AUD26-01-X29 | S2 | Rettet i #206 | Ingen headers mod clickjacking, ingen nosniff, ingen referrer-politik |
| F-AUD26-03-CI | S2 | Registreret | Cirka 420 Playwright-tests sprunget over i en grøn E2E-kørsel |
| F-AUD26-04-O02 | S3 | Rettet i #206 | Testmønster ramte et tidsstempel |

Åbne S0/S1 fra tidligere:
- Rettet, men ikke lukket af verifier: F-HOT16-01, F-JE-01 til -05, F-FIX18-01, F-FIX20-01 og F-VF-01.
- Afventer beslutning: F-PBQ-06 og F-PS-02.

S2/S3 i alt: 43 S2 og 32 S3 med status «new», 21 med status «fixed».

## Sikkerhed, tilgængelighed, ydeevne og gendannelse
- **Sikkerhed (ASVS 5.0, afgrænset):**
  - X20/X29-sweeps: alle `/operator/outreach/*` afviser roller, der ikke er operatør.
  - Tenant-sweepet omfatter de nye ruter.
  - Sikkerhedsheaders er tilføjet.
  - Der er ikke lavet en fuld CSP.
- **Tilgængelighed:** Der er ikke lavet nogen manuel gennemgang i denne kørsel.
- **Ydeevne:** Ingen belastningstest. Kun stikprøver med GET.
- **Gendannelse:** Ingen øvelse i gendannelse fra backup.

## Integrationer
Alt er testet mod fakes. Ingen test i udbydernes sandkasser: Stripe test mode, Vapi/Twilio, Resend og kalendere.

## Menneskelig accept
Ingen uafhængig verifier har kørt i auditten. qa-lead havde intet Agent-værktøj, og en verifier-kørsel på PR #206 er startet bagefter af hovedsessionen. Der er ingen menneskelig accepttest.

## Beslutninger til Fürster
1. F-AUD26-02: **besluttet A** (SMS-kode først), 12/11.
2. Er C09, C15, B03–B05 og M04 krav til lanceringen, når Erhverv kun har én plan?
3. F-PBQ-06: Må plan-apps fortsætte efter prøveperioden?
4. F-PS-02: Er `CLIENT_IP_SECRET` sat i produktion?
5. Skal qa-catalog blokere igen?
6. Resten: F-BQ-001, F-BQ-005, F-E2A-08, F-VER2-01 og F-VR-02.

## Ikke-blokerende beslutninger (ikke defekter)
- Travelpayouts B: scriptet kun på /privat, bag flag (#205).
- PDF uden tekstlag og uden OCR er accepteret.
- Én plan for Erhverv.

## Deployment-tjekliste (almindelige trin)
1. Fürster merger, når CI er grøn.
2. Kør `curl -sD - https://dialogbot.app/login` og tjek, at X-Frame-Options og CSP frame-ancestors er med.
3. Tjek, at kundernes webchat stadig åbner.
4. Tjek, at schema-head er grøn.

## Lanceringsblokkere
1. F-AUD26-02: SMS-koden skal bygges og verificeres.
2. P0/P1-scope skal besluttes for C09, C15, B03–B05 og M04, og der skal være PASS-evidens for hvert påkrævet P0/P1-scenarie. Det gælder også de ikke-implementerede H01, M03, M06, W04, W09, W13 og E07.
3. Uafhængig verifier skal lukke de 8 S0/S1-fund, der er rettet eller klar til rettelse, samt F-AUD26-01 og -04.
4. Privat-dybdekataloget skal køres på kandidaten.
5. Verifikation i udbydernes sandkasser.
6. Et deklareret belastningsbudget med målinger og en øvelse i gendannelse fra backup.
7. Beslutninger om F-PBQ-06 og F-PS-02.

## Genkørsel
Se `README.md`, `execution-manifest.md` og `scripts/qa_audit_register.py` i denne mappe.
