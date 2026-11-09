# Miljøer og databaser

Sidst verificeret 2026-11-04. Det der **ikke** kan læses (miljøvariablers værdier) er markeret.

| Render-tjeneste | Rolle | Database | Hvordan det er fastslået |
|---|---|---|---|
| `dialogbot-api-staging` | API (FastAPI) og kører `alembic upgrade head` som pre-deploy | **Supabase `dialogbot-prod-fra`** (`dmnbphhocnmjiqtcjddg`, eu-central-1/Frankfurt, skema `dialogbot`) | Flyttet 2026-11-04 kl. 20.21 UTC (se nedenfor); `pg_stat_activity` i det nye projekt viser `dialogbot_app`/`dialogbot_migrate` fra Render. |
| `dialogbot-worker-staging` | Worker (`python -m app.worker.runner`): outbox + planlagte jobs hvert minut | Samme produktionsdatabase | Workerens fejl `column … does not exist` kom fra produktionsskemaet; kladderne i `social_posts` ligger i prod |
| `dialogbot-public-api` (i `infra/render.yaml`, ikke oprettet endnu) | Den offentlige API `api.dialogbot.app/v1` (`APP_SURFACE=public`, `docs/public-api.md`) | Samme produktionsdatabase (`DATABASE_URL` kopieres fra API-tjenesten); ingen egen migration – `/health/ready` svarer 503 indtil databasen står på buildets head | Blueprint; DNS `api.dialogbot.app` → tjenesten (CNAME til Render) skal oprettes, når tjenesten er |
| – | – | Supabase `dialogbot-staging` (`zofdupmpcokvcvstsozm`) | **Ubrugt/forældet**: Alembic `3c1d29602dcc`, 65 tabeller, ingen `social_*`-tabeller. Ingen tjeneste skriver til den. Må ikke bruges til at teste migrationer, før den er migreret frem. |

## Flytningen til Frankfurt (2026-11-04)

Render-tjenesterne kører i Frankfurt, men databasen lå i `eu-west-1` (Irland): 25–50 ms pr. tur-retur til databasen, som
hvert API-kald betaler flere gange. Supabase kan ikke flytte et projekt mellem regioner, så:

1. Nyt projekt `dialogbot-prod-fra` (`dmnbphhocnmjiqtcjddg`, eu-central-1, Micro). `infra/supabase-roles.sql` kørt (nye
   adgangskoder til `dialogbot_migrate`/`dialogbot_app`; kun i Render Environment).
2. Skemaet genskabt 1:1 fra det gamle projekt (120 tabeller, 240 FK, 267 indeks – kolonner/constraints/indeks md5-sammenlignet),
   Alembic sat til samme revision (`b4e8f2a6c1d3`).
3. Data kopieret med `postgres_fdw` fra det nye projekt mod det gamle (4 589 rækker, alle tabeller talt op mod kilden),
   derefter et delta-løb efter skiftet (0 nye app-rækker i vinduet). FDW-link, midlertidig læserolle og logtabel fjernet igen.
4. `DATABASE_URL` (API + worker) og `MIGRATION_DATABASE_URL` (API) peger nu på session-pooleren
   `aws-1-eu-central-1.pooler.supabase.com:5432` med `rolle.dmnbphhocnmjiqtcjddg` som brugernavn. Pre-deploy-migrationen kørte
   rent; `/health/ready` 200, DB-opslag svarer på ~40 ms serverside.

Det gamle projekt `dialogbot-prod` (`wpcrnfyhukjjpcgcvxkc`, eu-west-1) er **ikke** slettet – det er reserven, indtil
flytningen er bekræftet i drift. Betalte projekter kan ikke pauses; slet det fra Supabase-dashboardet (Settings → General), når
det ikke skal bruges mere (ellers ~10 USD/md. for compute). Ingen tjeneste skriver til det længere.

Tjenesternes *navne* siger "staging", men de **er** produktion. Omdøbning er en bevidst, separat beslutning (URL'er, DNS og
Vercel-miljøvariabler peger på dem).

Siden 9. november 2026 kører alle fire Dialogbot-tjenester (`dialogbot-api-staging`, `dialogbot-worker-staging`,
`dialogbot-browser-worker-staging`, `dialogbot-public-api`) med `APP_ENV=prod` – før stod de på `staging`, og admin viste
derfor «STAGING». Prod kræver det samme som staging (`SECRET_KEY`, ingen dev-værktøjer) og desuden rigtig e-mail
(`EMAIL_ADAPTER=resend`, som har været sat siden 6. oktober).

Det kan ikke verificeres fra kode eller via Render-/Supabase-forbindelserne, hvilken præcis `DATABASE_URL`/`MIGRATION_DATABASE_URL`
tjenesterne har – værdierne er hemmeligheder og læses ikke. Beviset ovenfor er indirekte (skema og data). Åbn Render →
tjenesten → Environment for at se værdierne.

## Roller og forbindelser

* `dialogbot_app` – appens runtime-rolle, via Supabase-pooleren. Ikke ejer, ikke `BYPASSRLS`.
* `dialogbot_migrate` – ejer tabellerne; bruges kun af pre-deploy-kommandoen (`MIGRATION_DATABASE_URL`, direkte forbindelse).
* Appen bruger hverken Supabase Auth eller PostgREST; `anon`/`authenticated` har ingen rettigheder i skemaet `dialogbot`.

## Migrationer og udrulning

1. Render kører `DATABASE_URL="$MIGRATION_DATABASE_URL" alembic upgrade head` som pre-deploy, før den nye instans overtager.
2. Under en rullende udrulning kører den gamle worker/API stadig mod det nye skema i op til nogle minutter. Fejlen
   `column campaigns.package_net_minor does not exist` (2026-10-28 fra kl. 10.19) var præcis det: migrationen
   `1e8e65047603` omdøbte kolonnen til `call_net_minor`, og den gamle worker-instans spurgte stadig efter det gamle navn.
   Migrationen **var kørt** (produktionsdatabasen stod på head hele tiden); der var intet at køre om.
3. Derfor: omdøb/fjern aldrig en kolonne i samme udrulning som koden holder op med at bruge den (først tilføj + dobbeltskriv,
   så skift kode, så fjern i en senere udrulning).
4. Workeren sammenligner nu databasens revision med sin egen kode før hvert planlagt job og **pauser** dem (log
   `worker.schema_mismatch`) i stedet for at fejle på hver forespørgsel.
5. `.github/workflows/deploy-check.yml` kører hver time (og på forlangende) og fejler, hvis den kørende API ikke står på samme
   Alembic-head som commit'en (`scripts/check_live_schema.py`). `tests/test_schema_head.py` fejler, hvis der er mere end ét head
   eller databasen efter migration ikke står på kodens head.

## Moms og valuta (markeder)

Tre miljøvariabler styrer momsen; de skal stå ens på API og worker (workeren laver månedsfakturaerne). Regler og
opsætning: `docs/markets.md`.

| Variabel | Standard | Betydning |
|---|---|---|
| `STRIPE_TAX_ENABLED` | `false` | `true`: Stripe Tax afgør al moms (Erhverv-fakturaer og Privat Checkout får `automatic_tax` og SaaS-skattekoder). Sæt først efter Stripe Tax er aktiveret i Stripe-kontoen (afsnittet «Stripe Tax setup» i `docs/markets.md`) – ellers afviser Stripe kaldene. |
| `PRIVAT_EU_VAT_MODE` | `danish` | Uden Stripe Tax: `danish` = 25 % dansk moms til alle EU-forbrugere (under 10.000 EUR/år); `destination` = forbrugerens lands sats (kræver OSS-registrering). |
| `NO_VOEC_REGISTERED` | `false` | Uden Stripe Tax: `true` = 25 % norsk moms på norske forbrugere (efter VOEC-registrering, påkrævet over 50.000 NOK/år). |
