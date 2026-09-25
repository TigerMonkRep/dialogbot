# Slutrapport — etape 1: fundament og personlig opsætning

Dato: 25. september 2026. Repository: dette (nyoprettet; der fandtes ingen eksisterende kode).

## 1. Hvad er ændret (fra tomt repository)

- **Repository og stack**: Python 3.12, FastAPI, SQLAlchemy 2.1 (sync), Alembic, PostgreSQL 16, psycopg 3, pwdlib/argon2, structlog, pytest, ruff. Alle versioner låst i `requirements.lock`. CI i GitHub Actions med PostgreSQL-service.
- **Migration** `94af55693109_stage1_foundation` (19 tabeller) — verificeret fra tom database lokalt og i test/CI; `alembic check` bekræfter ingen drift.
- **Identitet**: registrering, login/logout, e-mailbekræftelse, glemt/nulstil adgangskode, sessioner. Opake sessionstokens (kun hash gemmes), engangstokens med formål og udløb.
- **Arbejdsrum og adgang**: arbejdsrum, medlemskab, roller (ejer/admin/medarbejder/læser) med eksplicit matrice, invitationer (token, udløb, tilbagekald, resend, accept med e-mailmatch, single-use), sidste-ejer-beskyttelse, audit-log.
- **Virksomhed**: profil (manuel opsætning uden URL), flere/egne kategorier, mål/kapabiliteter/vejledningsmåde, fire sprogniveauer. Optimistisk versionering.
- **Viden**: versionerede emner (kladde → gennemgang → godkendt → superseded), kun én åben kladde og ét godkendt pr. emne (databasegaranteret), assistent-endpoint med udelukkende godkendt viden, K04-tilbudsregel (≥ 40 m², inklusive datoer).
- **Opsætningsplan (G01–G08)**: serverberegnet plan med nødvendige/valgfrie trin, afhængigheder, rettighedsblokering, `not_available` for ikke-implementerede kapabiliteter, ærlig procent, næste handling, gem/genoptag, tildeling (G07), tjek med scope/miljø/konfigurationsversioner/evidens og målrettet forældelse ved ændringer. Aktivering er særskilte kommandoer (svarer 501).
- **Varige operationer**: transaktionel outbox, worker med lease/backoff/retry/genoptagelse, idempotensnøgler med payload-hash, simuleret e-mailadapter med idempotent levering.
- **Drift**: `/health/live`, `/health/ready` (database + migrationshead), JSON-logs med request-id, ensartede fejlsvar, OpenAPI eksporteret til `docs/openapi.json`.
- **Demo**: deterministisk seed (to arbejdsrum, fixtures fra pakken), dokumenteret Python-klient og reproducerbart demoforløb (`client/demo_flow.py`; output i `docs/demo-flow-output.txt`).
- **Prisregler**: de afstemte penge-/tvist-/beregnerregler som rene funktioner med tests (ikke eksponeret i API).

Omfang: ca. 5.600 linjer Python (app, migration, scripts, klient, tests), 50 API-stier.

## 2. Acceptkriterier

| # | Kriterium | Resultat | Evidens |
|---|---|---|---|
| 1 | Bruger fra A kan ikke liste/læse/redigere/godkende B's objekter | **Bestået** | `test_workspace_a_cannot_touch_workspace_b` (liste, læs, redigér, godkend; både under B's og A's arbejdsrum → 404) |
| 2 | Medarbejder/læser kan ikke godkende viden, tildele højere rolle eller ændre aftaler | **Bestået** | `test_staff_cannot_approve_or_change_roles`, `test_admin_cannot_escalate_to_owner_and_last_owner_protected`; finansielle aftaler findes ikke endnu — kapabiliteten `agreements.edit` er reserveret til ejer |
| 3 | Invitation: rigtigt arbejdsrum, single-use, udløb/tilbagekald, ingen abonnement | **Bestået** | `test_invitation_single_use_correct_workspace_no_subscription`, `test_expired_and_revoked_invitations_are_rejected` (arbejdsrumsantal uændret) |
| 4 | Manuel opsætning uden URL, flere/egne kategorier, separate sprog | **Bestået** | `test_manual_setup_without_url_multiple_categories_separate_languages` |
| 5 | Gem/genoptag i ny session åbner korrekt næste trin | **Bestået** | `test_resume_after_new_session`; demoforløbet (logout/login → samme `next_action`) |
| 6 | Assistent-endpoint kun godkendt viden; ny kladde rører ikke publiceret version | **Bestået** | `test_assistant_endpoint_only_approved_and_new_draft_keeps_active` |
| 7 | Kampagne-only uden telefon/kalender; ikke-implementeret integration blokerer aktivering | **Bestået** | `test_campaign_only_plan_has_no_phone_or_calendar_tasks` (501 ved tjek og aktivering; intet registreres) |
| 8 | Ændring forælder kun afhængige tjek | **Bestået** | `test_config_change_stales_dependent_checks_only` (sprog → kun sprogtjek; viden → kun videnstjek; profil forbliver bestået) |
| 9 | Idempotensnøgle og worker-genlevering giver ingen dobbelt effekt | **Bestået** | `test_idempotency_key_replays_and_rejects_changed_payload`, `test_worker_outbox_retry_and_no_duplicate_delivery` (retry, lease-udløb, tvungen genlevering → én levering), `test_failed_after_max_attempts` |
| 10 | Migrationer fra tom database; tests og CI bestået | **Bestået lokalt**; CI-workflow er skrevet men ikke kørt i GitHub (intet remote i denne session) | `tests/conftest.py` (drop schema → `alembic upgrade head`), `test_migrations_applied_and_health` |

## 3. Testresultater

`pytest` mod PostgreSQL 16.15: **26 bestået, 0 fejlet** (~16 s). `ruff check`: ingen fejl. `alembic check`: ingen drift. Demoforløb (`client/demo_flow.py`) mod kørende API + worker: gennemført, exit 0.

Tests pr. område: identitet/adgang 10, opsætning/viden 7, drift/regler 8, plus regelmodul for penge.

## 4. Kendte begrænsninger og ærlig status

- **Ikke browserafprøvet**: der er ingen frontend. De 44 design-HTML-filer i pakken er reference; ingen er forbundet til API'et. Frontendarbejdet (ruter, tilstande, tastaturnavigation, viewports) er en særskilt opgave og skal bruge `client/dialogbot_client.py` som kontraktreference.
- **Ingen eksterne integrationer**: telefoni, kalender, betaling, AI-samtale, web-widget, kildeimport og produktions-e-mail er `not_implemented`. E-mail findes kun som simuleret adapter (gemmer i databasen). Prod nægter at starte uden en rigtig mailadapter — og da ingen findes, kan denne etape ikke deployes med mailfunktion.
- **Ikke deployet**: ingen eksterne ressourcer er oprettet; Render/hosting er ikke berørt. Konfigurationen er klar til webservice + worker som separate processer.
- **CI ikke kørt eksternt**: workflowet er skrevet og de samme trin er kørt lokalt.
- **Delvise krav**: O02 (kun manuel viden), O03 (mål som data), O07/G02/G03/G04/G06/G08 (serverdelen findes; forklaringer/eksempler er frontend), S08 (profilredigering via API mangler), K01/K03/K05 (ingen kilder/konfliktdetektion).
- **Operatøradgang (M02), supportadgang og RLS** er ikke implementeret; arbejdsrumsadskillelse hviler på applikationslaget og constraints (testet).
- **Fixtures**: seed bruger pakkens fixtures, men tvist-/kampagnefixtures har ingen domænemodel endnu; kun de rene regler findes.

## 5. Anbefalet næste etape

**Etape 2 — Reception og daglig drift** (jf. backendplanens §8): godkendt assistent (O05: manuskript, hilsen, fallback som versioneret viden), samtaler/leads/opgaver (separate felter for kvalificering, pipeline og afregning), bestilt callback (W03–W06, R03) med verifikation, lead-godkendelse som idempotent domænehandling med aftaleversion, telefoni- og AI-adapter med reel kapabilitetsverifikation (så `reception.test_call` og `activation.reception` kan gennemføres), samt daglige rapporter. Grundlaget er på plads: kapabilitetsregistret, tjek med evidens, outbox/worker, audit og rettigheder skal blot udvides — ikke omskrives.

Sekundært, parallelt: frontend mod den eksporterede kontrakt (start med A01–A06, O01–O04, K01/K03/K05, G01/G05/G07) og opsætning af GitHub-remote så CI kører.
