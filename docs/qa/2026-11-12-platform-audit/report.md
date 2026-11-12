# Platform-audit Dialogbot – 12/11-2026

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
