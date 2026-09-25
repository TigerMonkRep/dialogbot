# ADR-001 — Fundament for Dialogbot-backenden (etape 1)

Dato: 25. september 2026. Status: vedtaget for etape 1.

## Kontekst

Repositoriet var tomt. Afleveringspakken angiver en pragmatisk standardstack (FastAPI, PostgreSQL, SQLAlchemy, Alembic, separat worker med outbox, pytest, GitHub Actions) og en række regler, som backenden skal håndhæve fra etape 1: arbejdsrumsadskillelse, roller, godkendt viden, serverberegnet opsætningsplan, varige operationer, ærlig integrationsstatus.

## Beslutninger

### 1. Modulopdelt monolit i Python/FastAPI, synkron SQLAlchemy 2.x, én PostgreSQL

Begrundelse: mindst mulig bevægelig infrastruktur; alle invarianter kan udtrykkes som constraints og partielle unikke indekser i én database; integrationstests kan køre mod en rigtig PostgreSQL uden mocks. Sync ORM valgt frem for async, fordi ingen del af etape 1 er I/O-bundet ud over databasen, og fordi låsning (`FOR UPDATE`, `SKIP LOCKED`) og transaktionsgrænser er lettere at ræsonnere om. Kan revurderes for telefoni/webhooks i senere etaper.

Moduler: `identity`, `workspaces`, `business`, `knowledge`, `setup`, `integrations`, `health`, `devtools`, `billing` (kun rene regler). Tværgående: `core/auth`, `core/errors`, `core/idempotency`, `core/outbox`, `core/audit`, `core/logging`.

### 2. Autentifikation: argon2 (pwdlib) + opake serverside-sessioner

- Adgangskoder hashes med argon2id via `pwdlib` (vedligeholdt bibliotek; ingen egen kryptografi).
- Sessioner er 256-bit tilfældige tokens; kun SHA-256 gemmes (`sessions.token_hash`). Bearer-header. Udløb, tilbagekaldelse (logout, reset) og "vis mine sessioner" (S08) understøttes.
- Fravalgt: JWT. Begrundelse: sessioner skal kunne tilbagekaldes øjeblikkeligt, og der er ingen frontend/gateway, som JWT'ers statsløshed gavner endnu. CSRF-model fastlægges sammen med den faktiske frontend (Bearer i header er ikke CSRF-følsom).
- `AUTH_PROVIDER=external` (OIDC) er reserveret i konfigurationen og **fejler lukket**: processen starter ikke.
- Engangstokens (verificering, nulstilling) har eksplicit `purpose`, udløb og `used_at`; invitationer har egen tabel. Tokens er ikke udskiftelige på tværs af formål.

### 3. Arbejdsrumsadskillelse på tre lag

1. Alle arbejdsrumsruter er `/workspaces/{workspace_id}/…`; dependency `get_workspace_context` slår medlemskab op pr. request og svarer `404` for ikke-medlemmer (ingen eksistenslækage).
2. Alle objektopslag sker med `id AND workspace_id` (`get_scoped`); fremmede id'er giver `404`, også når de præsenteres under kaldernes eget arbejdsrum.
3. Fremmednøgler med `ON DELETE CASCADE` og unikke constraints er arbejdsrumsafgrænsede.

PostgreSQL row-level security er ikke aktiveret i etape 1 (applikationen bruger én rolle); det kan lægges på som yderligere forsvar, når workers og migrationsrolle er afklaret.

### 4. Roller og rettigheder som en eksplicit matrice

`PERMISSIONS` i `app/core/auth.py` afbilder kapabilitet → mindste rolle (owner > admin > staff > reader). Ingen kan tildele en rolle over sin egen; kun ejere kan tildele/fratage ejerrollen; den sidste ejer er beskyttet. Invitation opretter medlemskab, aldrig arbejdsrum eller abonnement.

### 5. Viden som versionerede emner med ét aktivt og højst én åben kladde

`knowledge_items` (identitet: arbejdsrum, art, nøgle) + `knowledge_versions` (draft → in_review → approved → superseded | rejected). Partielle unikke indekser garanterer ét `approved` og én åben kladde pr. emne, uanset samtidighed. Assistentens læsemodel (`/assistant/knowledge`) returnerer udelukkende `approved`. Godkendelse bumper `workspaces.knowledge_revision`, skriver audit og outbox og markerer afhængige tjek forældede. Manuel indtastning har `source_type=manual`; import/udtræk er ikke implementeret.

### 6. Opsætningsplanen beregnes serverside

`app/modules/setup/plan.py` udleder hver opgaves status fra domænedata (profil, kategorier, mål, sprog, godkendt viden, tjekresultater, integrationsregistret og kalderens rolle). Kun det, som ikke kan udledes, persisteres (`setup_task_states`: spring, tildeling). Nødvendige trin kan ikke springes over; procent er afledt af nødvendige, faktisk gennemførte trin. Trin, hvis kapabilitet ikke er implementeret, får `not_available` med begrundelse og blokerer aktivering. Kampagne-only arbejdsrum får ingen telefon-/kalendertrin.

### 7. Tjek med scope, tid, miljø, konfigurationsversioner og evidens

`check_results` gemmer `config_versions` (profil-, mål-, sprogversion, vidensrevision) og `evidence`. `invalidate_checks(changed_area)` markerer kun tjek, hvis `depends_on` omfatter det ændrede område, som `stale`. Tjek, der kræver en ikke-implementeret adapter, kan ikke køres (`501`) og registrerer intet — en simuleret test kan aldrig aktivere produktion.

### 8. Varige operationer: transaktionel outbox + idempotensnøgler

- Domæneændring og `outbox_events` skrives i samme transaktion; `dedupe_key` er unik pr. forretningshandling.
- Worker (`app/worker/runner.py`): `FOR UPDATE SKIP LOCKED`, tidsafgrænset lease, eksponentiel backoff, `failed` efter `max_attempts`, genoptagelse efter procesafbrydelse (udløbet lease). Handlers er idempotente via unikke constraints (`email_deliveries.outbox_event_id`).
- `idempotency_keys` (scope = bruger + arbejdsrum + endpoint, payload-hash) gemmes i samme transaktion som effekten; samme nøgle med andet payload → `409`.
- Der loves at-least-once, ikke exactly-once.

### 9. Integrationer som et ærligt kapabilitetsregister

`app/modules/integrations/registry.py` rapporterer hver adapter som `available | simulated | not_implemented` med miljø og note. Kun e-mail findes, og kun som `simulated` (gemmer i databasen; leverer intet). Planen og tjekkene læser registret. Ingen udbyder er valgt ved at stå i designet.

### 10. Konfiguration fejler lukket

`Settings` validerer ved opstart: prod kræver `SECRET_KEY ≥ 32`, `ENABLE_DEV_TOOLS=false` og en ikke-simuleret mailadapter — og da ingen sådan findes, kan prod ikke påstå mailevne. Seed nægter prod og installerer aldrig en kendt standardadgangskode.

### 11. Penge og prisregler holdes som rene funktioner uden endpoints

`app/modules/billing/money.py` koder de afstemte regler (heltal i minor units, netto/moms/brutto, Model A/B gensidigt udelukkende, kampagnepakke, tvist uden kreditnota) og testes mod fixtures fra `canonical-demo-data.json`. Det forhindrer, at etape 4 arver DB-001/DB-002 fra eksporten. Intet af det er eksponeret via API.

## Konsekvenser

- Én database og én kodebase gør etape 1 let at køre lokalt og i CI; skalering af telefoni/webhooks kan senere kræve egne processer, men outbox/worker-mønstret er allerede på plads.
- Frontend skal sende Bearer-token og `expected_version`; se `client/dialogbot_client.py`.
- Alle senere adaptere skal registreres i kapabilitetsregistret med reel verifikation, før planen kan markere de relaterede trin som gennemførte.
