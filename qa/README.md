# Dialogbot QA-hold – protokol

Holdet kører alle flows igennem for hvert scenarie, taler sammen om fund, får dem rettet og bevist rettet. Denne fil er kontrakten mellem agenterne. Agentfilerne ligger i `.claude/agents/`.

## Holdet

| Agent | Ansvar | Må ændre produktkode? |
|---|---|---|
| `qa-lead` | Planlægger bølger, fordeler scenarier, triagerer, beslutter go/no-go | Nej |
| `e2e-erhverv` | Alle erhvervsflows i browser (Playwright), desktop + mobil | Nej (kun tests) |
| `e2e-privat` | Alle Privat-flows inkl. prøveperiode, Butikken, ønskelister | Nej (kun tests) |
| `voice-qa` | Peter: reception, callback, kampagner, sprog, navne – uden at brænde opkald | Nej (kun evals) |
| `api-contract-qa` | FastAPI, public API v1, worker/outbox, migrationer | Nej (kun tests) |
| `billing-qa` | Alle beløb, Stripe test, moms, forbrug, refusion, tvister | Nej (kun tests) |
| `integrations-qa` | Google/Microsoft kalender, Twilio, Resend, 17TRACK, Duffel m.fl. – ærlig status | Nej (kun tests) |
| `security-privacy` | Tenant-isolation, roller, secrets, GDPR | Nej (kun tests) |
| `i18n-a11y-qa` | 8 sprog, tilgængelighed, performance, PWA | Nej (kun tests) |
| `fix-engineer` | Retter bekræftede fund med regressionstest | **Ja – som den eneste** |
| `verifier` | Uafhængig gentest; den eneste der lukker et fund | Nej |

Eksisterende designagenter (`ui-ux-engineer`, `art-director`, `designer`) bruges som rådgivere, når et fund er et smags- eller designspørgsmål.

## Arbejdsgangen (loopet)

```
qa-lead planlægger bølge ─▶ specialister tester parallelt ─▶ fund i qa/findings/
        ▲                                                         │
        │                                     qa-lead triagerer (dublet? alvor? ejer?)
        │                                                         │
 verifier lukker/genåbner ◀── fix-engineer retter + regressionstest
```

Et fund går gennem statusserne:
`new → confirmed → fixing → fixed → closed` (eller `reopened`, `cannot-reproduce`, `needs-decision`, `wont-fix`).

Et scenarie har status: `todo | running | pass | fail | blocked | not-implemented | flaky`.

## Beskeder mellem agenter

Agenterne taler sammen med SendMessage (eller via filerne, hvis beskeder ikke er tilgængelige). Altid dette format, så intet går tabt:

```
TIL: <agent>   FRA: <agent>   EMNE: <finding-id | scenario-id>
TYPE: finding | handoff | fix-ready | verdict | question | needs-decision
KORT: <én linje>
DETALJER: <trin, forventet, faktisk, sti til evidens>
NÆSTE: <hvad modtageren skal gøre>
```

Hver besked logges med én linje i `qa/ledger.md`.

## ID'er og filer

- Scenarier: `qa/scenarios.csv` – ID = krav-ID fra handoff (fx `A01`, `BK09`) eller `X..` for funktioner tilføjet efter handoff.
- Fund: `qa/findings/F-<løbenr>-<scenarie-id>.md` (skabelon: `_TEMPLATE.md`).
- Evidens: `qa/evidence/<scenarie-id>/` (trace, screenshot, log, transcript).
- Rapport: `qa/reports/<dato>-run.md`.

## Alvorsgrader

| Grad | Betyder | Eksempel |
|---|---|---|
| S0 | Penge, data, sikkerhed eller rigtige opkald/SMS går galt | Kunde A ser kunde B's opkald; forkert faktura; SMS sendt uden godkendelse |
| S1 | Et flow kan ikke gennemføres, eller UI lyver | Onboarding hænger; "Forbundet" på en integration, der ikke findes |
| S2 | Forkert, men der er en vej udenom | Forkert tom-tilstand, forkert sprog i en fejlbesked |
| S3 | Kosmetisk | Afstand, ikon |

## Miljø

**Vigtigt:** Render-tjenesterne `dialogbot-api-staging` / `dialogbot-worker-staging` og Supabase-projektet bag dem er **produktion**. QA må aldrig skrive til dem.

QA kører på:
1. **CI/lokal stak:** PostgreSQL i Docker, `alembic upgrade head`, API + worker med test-env, Next.js mod den lokale API. Data kun fra `canonical-demo-data.json`.
2. **Vercel preview** af fix-branchen (peger på QA-API'et, ikke produktion).
3. **Produktion:** kun læsende røgtest af offentlige sider (GET), ingen login, ingen formularer.

Eksterne tjenester: Stripe test mode, provider-sandkasser eller optagne fixtures. E-mail og SMS stopper i outbox/test-indbakke.

## Sikkerhedsregler (gælder alle agenter)

- Ingen rigtige opkald, SMS eller e-mails til rigtige personer. Eneste undtagelse: ét internt testopkald til Fürsters eget nummer, efter at han har skrevet ja i chatten.
- 93 70 34 33 og dens opsætning røres ikke.
- Ingen Stripe live, ingen opgraderinger, ingen køb.
- Secrets læses, printes og kopieres aldrig. Kontrollér kun at env-variablens *navn* findes.
- Ingen ændringer i Render/Vercel/Supabase-konfiguration.
- Produktbeslutninger (priser, juridisk tekst, Peters regler, Model A/B, K04 ≥ 40 m²) træffes af Fürster → `needs-decision`.

## Definition of Done for en kørsel

- Alle P0- og P1-scenarier `pass` med evidens, kørt 3/3 gange fra ren database.
- 0 åbne S0/S1-fund.
- CI grøn på fix-branchen, og alle rettelser har regressionstest.
- Ingen grønne stubbe: ikke-byggede integrationer står som `not-implemented`.
- Rapport til Fürster på dansk: hvad virker, hvad er rettet, hvad kræver hans beslutning, hvad blev ikke testet og hvorfor.
