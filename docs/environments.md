# Miljøer og databaser

Sidst verificeret 2026-10-28. Det der **ikke** kan læses (miljøvariablers værdier) er markeret.

| Render-tjeneste | Rolle | Database | Hvordan det er fastslået |
|---|---|---|---|
| `dialogbot-api-staging` | API (FastAPI) og kører `alembic upgrade head` som pre-deploy | **Supabase `dialogbot-prod`** (`wpcrnfyhukjjpcgcvxkc`, skema `dialogbot`) | `/health/ready` svarer med samme Alembic-revision som produktionsdatabasen; kun prod har `social_posts` m.fl. |
| `dialogbot-worker-staging` | Worker (`python -m app.worker.runner`): outbox + planlagte jobs hvert minut | Samme produktionsdatabase | Workerens fejl `column … does not exist` kom fra produktionsskemaet; kladderne i `social_posts` ligger i prod |
| – | – | Supabase `dialogbot-staging` (`zofdupmpcokvcvstsozm`) | **Ubrugt/forældet**: Alembic `3c1d29602dcc`, 65 tabeller, ingen `social_*`-tabeller. Ingen tjeneste skriver til den. Må ikke bruges til at teste migrationer, før den er migreret frem. |

Tjenesternes *navne* siger "staging", men de **er** produktion. Omdøbning er en bevidst, separat beslutning (URL'er, DNS og
Vercel-miljøvariabler peger på dem).

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
