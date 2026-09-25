# Dialogbot backend — etape 1: fundament og personlig opsætning

Status: **etape 1 implementeret og testet lokalt/CI; milepæl A (frontend + driftskonfiguration) i gang** — se `docs/implementation-progress.md`. Ikke deployet, ikke browserafprøvet.

Omfang i denne etape: konto → e-mailbekræftelse → arbejdsrum → virksomhedsprofil/kategorier → mål/sprog → manuel viden → godkendelse → personlig opsætningsplan med tjek → invitation af kolleger → gem/genoptag. To arbejdsrum kan ikke se hinandens data.

## Stack (låst i `requirements.lock`)

Python 3.12 · FastAPI 0.141 · SQLAlchemy 2.1 (sync) · Alembic 1.20 · PostgreSQL 16 · psycopg 3 · pwdlib/argon2 · structlog · pytest 9 · ruff. Arkitekturvalg: se [`docs/ADR-001-foundation.md`](docs/ADR-001-foundation.md).

## Kom i gang

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env            # ret DATABASE_URL
createdb dialogbot && createdb dialogbot_test
alembic upgrade head            # migrér fra tom database
uvicorn app.main:app --reload --port 8000     # API (OpenAPI: /api/v1/docs)
python -m app.worker.runner                   # outbox-worker (separat proces)
```

Klar-tjek: `curl localhost:8000/health/ready` → `{"status":"ok", "migration": <head>, ...}`.

### Demodata (aldrig i prod)

```bash
SEED_DEMO_PASSWORD='vælg-selv' python -m scripts.seed
```

Opretter to isolerede arbejdsrum med fixture-data fra afleveringspakken (`Fjord Gulvservice ApS` med godkendt viden inkl. K04-tilbuddet ≥ 40 m², og `Havnebord Café & Catering` med én kladde til gennemgang) samt brugere `owner|admin|staff|reader@fjordgulv.example` og `owner@havnebord.example`. Uden `SEED_DEMO_PASSWORD` genereres og printes en tilfældig adgangskode én gang. Seed nægter at køre med `APP_ENV=prod`.

### Reproducerbart demoforløb (hele etape 1 via API'et)

```bash
ENABLE_DEV_TOOLS=true uvicorn app.main:app --port 8000   # terminal 1
python -m app.worker.runner                                # terminal 2
python -m client.demo_flow                                 # terminal 3
```

Output fra en kørsel ligger i [`docs/demo-flow-output.txt`](docs/demo-flow-output.txt). Klienten [`client/dialogbot_client.py`](client/dialogbot_client.py) er den dokumenterede reference for, hvordan en frontend skal kalde backenden. Der er ingen frontend i dette repository; de 44 design-HTML-filer i afleveringspakken er visuel reference og er ikke omskrevet.

## Test og CI

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/dialogbot_test pytest
ruff check app tests scripts client
alembic check          # ingen drift mellem modeller og migrationer
```

Alle tests er integrationstests mod en rigtig PostgreSQL: skemaet droppes og migreres fra tom ved sessionsstart; tabeller tømmes mellem tests. CI (`.github/workflows/ci.yml`) kører lint, migration fra tom, `alembic check`, pytest og kontrollerer at `docs/openapi.json` matcher koden.

Testresultat ved aflevering: 26 bestået (se `docs/final-report.md`).

## Konfiguration

Alle værdier læses fra miljøet (`.env.example` er dokumenteret). Processen **nægter at starte** i prod uden `SECRET_KEY` (≥ 32 tegn), med `ENABLE_DEV_TOOLS=true`, eller med `EMAIL_ADAPTER=simulated`. `AUTH_PROVIDER=external` og `EMAIL_ADAPTER=smtp` er reserverede og fejler lukket, fordi de ikke er implementeret. Der findes ingen sti, hvor manglende konfiguration åbner et uautentificeret system.

## Roller

| Kapabilitet | reader | staff | admin | owner |
|---|:-:|:-:|:-:|:-:|
| Læse arbejdsrum, viden, plan, medlemmer | ✔ | ✔ | ✔ | ✔ |
| Redigere profil/kategorier/mål/sprog, oprette og indsende kladder, køre tjek, springe valgfrie trin over | | ✔ | ✔ | ✔ |
| Godkende/afvise viden, invitere, ændre roller (≤ egen), fjerne medlemmer, læse audit, aktivere (når implementeret) | | | ✔ | ✔ |
| Tildele/fratage ejerrolle, ændre finansielle aftaler (senere etape) | | | | ✔ |

Den sidste ejer kan hverken degraderes eller fjernes uden forudgående overdragelse. Se `app/core/auth.py::PERMISSIONS`.

## Vigtige API-konventioner

- Prefix `/api/v1`. Alle arbejdsrumsruter ligger under `/workspaces/{workspace_id}/…`; medlemskab slås op pr. request. Objekter fra andre arbejdsrum giver `404`.
- Fejl: `{code, message, field_errors, request_id}`; `X-Request-ID` i alle svar.
- Redigerbare indstillinger har `version`; `PUT` kræver `expected_version` → `409 version_conflict`.
- Effektfulde kommandoer (invitation, godkendelse) accepterer `Idempotency-Key`; samme nøgle + andet payload → `409 idempotency_payload_mismatch`.
- Tokens til verificering, nulstilling og invitation udleveres kun i (simulerede) e-mails; API-svar og logs indeholder dem aldrig. Kun SHA-256 gemmes.
- `/api/v1/dev/mailbox` og `/api/v1/dev/outbox` findes kun med `ENABLE_DEV_TOOLS=true` (aldrig i prod) og viser kun den indloggede brugers egne mails.

Fuld kontrakt: [`docs/api-contract.md`](docs/api-contract.md) og [`docs/openapi.json`](docs/openapi.json).

## Dokumenter

- `docs/ADR-001-foundation.md` — arkitektur og begrundelser
- `docs/api-contract.md` — endpoints, tilstande, fejlkoder
- `docs/requirements-status.md` — kravstatus (kun faktisk implementeret omfang)
- `docs/final-report.md` — slutrapport for etapen

## Frontend (`web/`)

Next.js 16 + TypeScript + Tailwind 4. Kører mod API'et via same-origin BFF (`/api/backend/*`) med session i httpOnly-cookie.

```bash
cd web && npm ci && API_BASE_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Drift: `infra/render.yaml` (API + worker), `infra/supabase-roles.sql`, `web/vercel.json`. Vejledning: `docs/services-setup.md`, `docs/environment-variables.md`, `docs/ADR-002-hosting-and-services.md`.
