# QA 2026-11-13 – belastningstest (50 kunder / 10 samtidige opkald) og backup-restore

Mærkat på alt midlertidigt: **loadtest-2026-11-13**. Produktion (Render `srv-dar72rbncjis73ccsi10` / `srv-dar72rbncjis73ccsi0g`,
Supabase `dialogbot-prod-fra`, Vercel `dialogbot`) er **ikke** ændret, genstartet eller belastet. Mod produktion er der kun
kørt læsende SQL (`SELECT`) og hentet Render-metrikker.

## Kort konklusion

| Krav | Resultat |
|---|---|
| 50 kunder + 10 samtidige opkald med den kode der ligger i `main` nu | **Ikke opfyldt.** API'et går i stå efter 1–2 minutter: 21–91 % fejl (30 s timeouts), og 16–83 % af opkaldsrapporterne (`end-of-call-report`) blev aldrig gemt. |
| Samme last med én lille rettelse (Vapi-webhooken som synkron handler, se §1.4) | **Funktionelt opfyldt:** 0,0–0,4 % fejl, 0 tabte opkald, 0 dobbeltbehandlinger. Svartiderne (p95 4–6 s) er dog for høje til telefoni – se anbefalinger. |
| Dobbeltbehandling | **Ingen** i nogen kørsel: 1.184 opkald, ~250 bevidst dobbelt-sendte rapporter → 0 dubletter af opkald, samtaler, leads, opgaver, webhook-events eller outbox-jobs. |
| Backup-restore | **Ikke udført** – værktøjerne kan hverken gendanne til nyt projekt eller slette et projekt. Trin til ejeren og tjek-SQL med produktionens tal er nedenfor (§2). |

## 1. Belastningstest

### 1.1 Hvor testen kørte – og hvorfor ikke i skyen

Planen var et midlertidigt Render-miljø (Postgres + web + worker fra `main` med fakes). Render-værktøjerne kan **oprette** men
**ikke slette eller suspendere** ressourcer, og de udleverer ikke databasens adgangskode/forbindelsesstreng. Det blev opdaget
efter at databasen var oprettet. Derfor blev der **ikke** oprettet web-service eller worker på Render (de kunne ikke slettes
igen), og hele testen kørte **lokalt** i `/home/claude`:

* PostgreSQL 16 lokalt, Alembic-head fra branchen (`c5e1f7a3d9b2`), 50 seedede arbejdsrum.
* API som i produktion: `uvicorn app.main:app --workers 2` (produktion: Render *Standard* = 1 CPU / 2 GB, 2 workers).
  Kørsler med `taskset` på 1 hhv. 2 CPU-kerner. Worker (`python -m app.worker.runner`) på én kerne.
* Fakes: `APP_ENV=test`, `TELEPHONY_PROVIDER=fake`, `CONNECTORS_PROVIDER=fake`, `AI_PROVIDER=fake`, `TTS_ENGINE=fake`,
  `EMAIL_ADAPTER=simulated`, ingen Stripe-nøgle, Vapi-secret = testværdien fra `.github/workflows/e2e.yml`.
  Ingen rigtige opkald, SMS'er eller mails.
* **Forbehold:** maskinen var delt med andre sessioners pytest/Playwright-kørsler (load average 20–24 på 16 kerner). Absolutte
  svartider er derfor støjfyldte og nok pessimistiske; **de kvalitative fund (sammenbrud vs. intet sammenbrud, tabte opkald,
  dubletter, forbindelsestal) er robuste** og gentaget i flere kørsler.

### 1.2 Data og trafik (scripts i `scripts/loadtest/`)

* `seed.py` – 50 arbejdsrum (`lt-001…lt-050`, 10 brancher × 10 byer), hver med ejer + medarbejder, virksomhedsprofil,
  6 godkendte vidensposter, bekræftet abonnementsaftale (model A), aktivt platformsnummer (Vapi-id `lt-pn-NNN`), aktiv
  telefoniopsætning og aktiveret webchat. Nægter at køre med `APP_ENV=prod`.
* `load.py` – asyncio/httpx. Nægter produktionens værter.
  * **10 samtidige opkald** i løkke: `assistant-request` → `status-update` → `tool-calls` → `status-update(ended)` →
    `end-of-call-report` (signeret med e2e-secret), ~3 s mellem trinene. 20 % af rapporterne sendes **to gange samtidigt**
    (som når Vapi gentager) for at fange dobbeltbehandling.
  * **50 webchat-besøgende** (én pr. kunde): status → ny samtale → 2–4 beskeder (AI svarer synkront i requestet) → 30 % lægger
    kontaktoplysninger (lead + opgave + «ny henvendelse»-mail via outbox).
  * **50 indloggede ejere** der poller dashboardet (overview, notifications, feed, calls, reception, conversations, me) hvert ~10 s.
  * Samlet ~20–30 requests/s.
* `sample_db.py` – forbindelser (`pg_stat_activity`) og outbox-kø hvert 2. s.
* `verify.sql` – dubletkontrol (læsende).
* `slow_app.py` – kun til test: lægger 3 s (±40 %) simuleret modellatens på den falske AI, så man ser hvad rigtige
  modelsvar gør ved tråde og DB-forbindelser.

### 1.3 Resultater

Tider i ms. «Tabt» = opkald hvor `end-of-call-report` blev sendt men aldrig endte i `calls`.

| Kørsel | Konfiguration | Varighed s | req/s | p50 | p95 | p99 | Fejlrate | p95 assistant-request | p95 end-of-call | p95 chatbesked | Maks DB-forb. | Maks outbox-kø | Opkald / tabt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | `main`, alle kerner, pool 5+5 | 300 | 12,3 | 81 | 30.008 | 30.015 | **21,1 %** | 30.007 | 30.010 | 30.005 | 21 | 0 | 107 / **17** |
| B | `main`, 1 kerne (≈ Render Standard), pool 5+5 | 300 | 4,1 | 30.004 | 30.024 | 30.059 | **90,9 %** | 30.022 | 30.034 | 30.010 | 21 | 0 | 30 / **25** |
| K1 | `main`, kun chat + dashboard (kontrol) | 90 | 27,1 | 101 | 379 | 566 | 0 % | – | – | 445 | 15 | 0 | – |
| K2 | `main`, kun 10 opkald (kontrol) | 90 | 5,7 | 66 | 261 | 1.782 | 0 % | 1.782 | 333 | – | 13 | 0 | 98 / 0 |
| C | `main`, pool 20+10 | 120 | 29,6 | 297 | 1.367 | 2.322 | 0 % | 2.077 | 1.039 | 1.409 | **51** | 0 | 115 / 0 |
| D | **rettelse**, 1 kerne, pool 5+5 | 300 | 23,4 | 1.058 | 4.246 | 6.427 | 0,03 % | 4.002 | 4.622 | 4.694 | 22 | 2 | 191 / 0 |
| E | **rettelse**, 2 kerner, pool 5+5 | 300 | 19,8 | 1.861 | 5.628 | 7.853 | 0,4 % | 6.062 | 5.917 | 5.741 | 21 | 2 | 145 / 0 |
| F | rettelse + AI 3 s, pool 5+5 | 180 | 19,2 | 1.936 | 6.765 | 9.640 | 0 % | 3.283 | 9.262 | 8.711 | 21 | 2 | 97 / 0 |
| G | rettelse + AI 3 s, pool 20+10 | 180 | 23,9 | 821 | 4.808 | 6.067 | 0,02 % | 2.207 | 2.211 | 5.770 | **57** | 2 | 140 / 0 |
| H | rettelse, **dobbelt last** (20 opkald/100/100), pool 20+10 | 180 | 25,9 | 4.643 | 12.976 | 18.603 | 0,4 % | 12.280 | 13.206 | 13.015 | **61** | 4 | 107 / 1 |

Dublet-/integritetstjek efter alle kørsler (`verify.sql`): 1.184 opkald = 1.184 unikke opkalds-id'er, 1.184 telefonsamtaler,
1.184 leads, 1.184 opgaver, 1.184 webhook-events; **0** dubletter af nogen af dem; 3.321 webchatsamtaler, 8.873 AI-svar;
477 outbox-jobs (alle «ny henvendelse»-mails), alle `done` i første forsøg, 0 fejlede, 0 dedupe-dubletter, kø maks. 4 og
ældste ventende job maks. ~2 s. **Workeren er ikke en flaskehals** ved denne last (bemærk: opkald lægger i dag ingen
outbox-jobs; det gør kun webchat-kontakter og mails).

### 1.4 Flaskehalse

1. **Kritisk – Vapi-webhooken blokerer event-loopet.** `POST /api/v1/webhooks/vapi` (`app/modules/telephony/router.py`) er
   `async def`, men laver synkront databasearbejde (SQLAlchemy) direkte på event-loopet. Når alle 10 forbindelser i en
   uvicorn-proces' pool er i brug, venter webhooken op til 30 s (`pool_timeout`) **på selve event-loopet**. Imens kan de
   synkrone endpoints i threadpoolen ikke blive færdige og give deres forbindelse tilbage (oprydningen kører via loopet) –
   alle forbindelser står `idle in transaction`, og hele processen hænger (også `/health/ready`). Kontrolkørsler K1/K2 viser
   at hver trafiktype alene er fin; det er kombinationen af opkald + almindelig trafik der vælter det. Konsekvens i
   produktion: opkaldsrapporter går tabt (17 og 25 i kørsel A/B), og `assistant-request` svarer for sent – den der ringer
   får fejlbesked/stilhed. Samme mønster findes i 16 andre `async def`-endpoints med `get_db` (bl.a. `/webhooks/stripe`,
   `/webhooks/resend`, `/elevenlabs/*`, `outreach/webhooks/events`, support-tickets, fil-uploads).
   *Rettelse afprøvet lokalt (ikke committet i denne PR):*

   ```diff
   +async def _raw_body(request: Request) -> bytes:
   +    return await request.body()
   +
   +
    @webhook_router.post("/vapi")
   -async def vapi_webhook(request: Request, db: OrmSession = Depends(get_db),
   -                       authorization: str | None = Header(default=None),
   -                       x_vapi_secret: str | None = Header(default=None)):
   +def vapi_webhook(raw: bytes = Depends(_raw_body), db: OrmSession = Depends(get_db),
   +                 authorization: str | None = Header(default=None),
   +                 x_vapi_secret: str | None = Header(default=None)):
        vapi.verify(authorization, x_vapi_secret)
        try:
   -        body = json.loads(await request.body())
   +        body = json.loads(raw)
   ```

   Med den: 0 tabte opkald og ≤ 0,4 % fejl (D–H).
2. **DB-forbindelser / Supabase.** Produktionen (`dialogbot-prod-fra`, Micro) har `max_connections = 60`, og app-rollen
   `dialogbot_app` havde allerede **15 forbindelser via Supavisor** i hvile (læst 13/11 kl. 12:00 UTC). Hver API-proces må
   bruge 5+5 = 10, dvs. 20 for API'et + worker + `dialogbot-public-api` (2 workers mere) – allerede ved grænsen for
   Supavisors session-pool. En større pool (C, G, H: 51–61 forbindelser) fjerner køen men passer ikke til Micro.
3. **Synkrone AI-kald holder en DB-forbindelse.** Webchat-svaret kaldes inde i requestet med åben session. Med 3 s modellatens
   (F) stiger chat-p95 til 8,7 s og opkaldsrapporter til 9,3 s, fordi opkald og chat deler de 10 forbindelser.
4. **CPU.** Ved dobbelt last (H) flader gennemstrømningen ud ved ~26 req/s for 2 processer, og svartiderne stiger til
   10–20 s. På den støjende maskine er 1 vs. 2 kerner ikke til at skelne (D vs. E), så tallet er et loft for denne test, ikke
   en præcis kapacitet for Render.
5. **Første `assistant-request` efter opstart** tager 1–2 s (opvarmning af prompt/viden) – relevant ved deploy midt på dagen.

### 1.5 Anbefalinger (i prioriteret rækkefølge)

1. **Ret Vapi-webhooken** som vist ovenfor (og gennemgå de 16 andre `async def` + `get_db`-endpoints på samme måde). Det er
   det eneste der skal til for at 50 kunder / 10 opkald ikke vælter. Tilføj en regressionstest der sender samtidige
   webhooks + almindelige requests (fx `scripts/loadtest/load.py --duration 60` i CI mod e2e-stakken).
2. **Supabase-forbindelser:** skift app-rollens `DATABASE_URL` til Supavisor **transaction mode** (port 6543) for API og
   worker, *eller* opgradér compute fra Micro (60 forbindelser) til **Small** (90) – og sæt `DB_POOL_SIZE=8`,
   `DB_MAX_OVERFLOW=4` pr. proces. Hold summen (API 2 × 12 + public-api 2 × 12 + worker 2 + Supabase' egne ~8) under
   grænsen.
3. **Tag AI-kaldet ud af DB-sessionen** i webchatten (læs viden → luk/commit → kald model → åbn kort session og gem svaret),
   så modellatens ikke binder forbindelser.
4. **Render-plan for API'et:** Standard (1 CPU) var mættet i testen. Anbefaling: **Pro (2 CPU / 4 GB) med 4 uvicorn-workers**
   eller 2 × Standard-instanser – men først efter punkt 1–2, ellers flytter det bare problemet til databasen.
5. **Worker:** 1 × Starter er nok ved denne last (kø ≤ 4, ældste job ≤ 2 s). Revurdér når kampagner/opkald lægger outbox-jobs.
6. Sæt en **Vapi-timeout-alarm**: log/metrik når `assistant-request` tager > 2 s eller en `end-of-call-report` svarer 5xx.

### 1.6 Genkør testen

```bash
export APP_ENV=test AI_PROVIDER=fake TTS_ENGINE=fake TELEPHONY_PROVIDER=fake CONNECTORS_PROVIDER=fake EMAIL_ADAPTER=simulated
export DATABASE_URL=postgresql+psycopg://…/loadtest_local VAPI_SERVER_SECRET=<e2e-testværdi> LOADTEST_PASSWORD=<valgfri>
export PUBLIC_BASE_URL=http://localhost:8200 CREDENTIALS_KEY=<e2e-testværdi>
alembic upgrade head && python -m scripts.loadtest.seed --count 50
uvicorn app.main:app --port 8200 --workers 2 &  python -m app.worker.runner &
python -m scripts.loadtest.load --base http://localhost:8200 --duration 300 --out result.json
psql "$DATABASE_URL" -x -f scripts/loadtest/verify.sql
```

## 2. Backup-restore af produktionsdatabasen

### 2.1 Hvad værktøjerne kunne – og ikke kunne

* Supabase-værktøjerne har **ingen** «gendan backup / PITR til nyt projekt», ingen liste over backups og ingen sletning af
  projekter. `restore_project` er genstart af et *pauset* projekt og blev ikke rørt. En branch af produktionsprojektet ville
  være en ændring af produktionsprojektet og ville kun indeholde skema, ikke data – derfor ikke brugt.
* **Derfor er gendannelsen ikke udført, og RTO/RPO er ikke målt.** Intet blev oprettet hos Supabase.

### 2.2 Hvad der kunne verificeres (kun læsning)

* Produktion er `dialogbot-prod-fra` (ref `dmnbphhocnmjiqtcjddg`, eu-central-1, Postgres 17.11.0.011). Det gamle projekt
  `dialogbot-staging` har ingen app-forbindelser og sidste audit 26/9 – det kører dog stadig (koster ~10 USD/md).
* Organisationen er på **Pro**. Ifølge Supabase' dokumentation: dagligt backup, 7 dages historik, fysiske backups for
  Postgres ≥ 15.8.1.079 (opfyldt) → «Restore to a New Project» er tilgængelig. **PITR-status kan ikke læses** med
  værktøjerne. Uden PITR er **RPO op til 24 timer**.
* Custom roller (`dialogbot_app`, `dialogbot_migrate`) får **ikke** deres adgangskoder med i daglige backups – de skal
  nulstilles efter gendannelse (del af RTO).
* Udvidelser i produktion: pg_stat_statements, pgcrypto, plpgsql, postgres_fdw (ingen foreign servers), supabase_vault,
  uuid-ossp. Ingen pg_cron/pg_net-jobs der ville køre løs i en kopi.
* Referencetal fra produktion, 13/11-2026 kl. 12:00 UTC (til sammenligning efter gendannelse):

| Måling | Værdi |
|---|---|
| `dialogbot.alembic_version` | `1d2e6f8b0c4a` |
| Tabeller i skema `dialogbot` | 149 |
| users / workspaces / sessions | 7 / 5 / 25 |
| knowledge_versions | 57 |
| calls / conversations / conversation_messages | 60 / 60 / 1.180 |
| leads | 48 |
| outbox_events (nyeste) | 183 (13/11 08:15 UTC) |
| audit_log (nyeste) | 350 (13/11 08:58 UTC) |

### 2.3 Trin ejeren selv skal klikke (ca. 15–30 min, koster en Micro-instans ~0,014 USD/t mens kopien findes)

1. Notér klokkeslæt (start på RTO).
2. Supabase Dashboard → projekt **dialogbot-prod-fra** → *Database* → *Backups* → fanen **Restore to a New Project**.
3. Vælg nyeste daglige backup (eller et tidspunkt, hvis PITR er slået til). Godkend prisoverslaget. Navngiv gerne
   `loadtest-2026-11-13-restore`. Produktionen påvirkes ikke.
4. Når kopien er klar: notér klokkeslæt (RTO = trin 4 − trin 1, plus tiden for trin 5).
5. I kopien: *SQL Editor* → nulstil adgangskoder for `dialogbot_app` og `dialogbot_migrate` (kun hvis man vil forbinde en app –
   ikke nødvendigt for tjekket).
6. Kør i kopiens SQL Editor (kun læsning) og sammenlign med tabellen ovenfor. RPO (hvor gammel dataen er) =
   tidspunktet for øvelsen − `nyeste_audit`/`nyeste_outbox` i kopien, sammenholdt med de samme værdier i produktion:

   ```sql
   select (select version_num from dialogbot.alembic_version) as alembic,
          (select count(*) from information_schema.tables where table_schema='dialogbot' and table_type='BASE TABLE') as tabeller,
          (select count(*) from dialogbot.users) users, (select count(*) from dialogbot.workspaces) workspaces,
          (select count(*) from dialogbot.knowledge_versions) knowledge_versions, (select count(*) from dialogbot.calls) calls,
          (select count(*) from dialogbot.conversation_messages) messages, (select count(*) from dialogbot.leads) leads,
          (select max(created_at) from dialogbot.audit_log) nyeste_audit, (select max(created_at) from dialogbot.outbox_events) nyeste_outbox;
   ```
7. **Slet kopien bagefter:** kopiens *Project Settings* → *General* → *Delete project*.

Anbefaling: slå **PITR** til (Supabase add-on) når der kommer betalende kunder – det bringer RPO fra op til 24 t ned til minutter.

## 3. CLIENT_IP_SECRET (kun navne)

* **Vercel** (`dialogbot`): findes – type *sensitive*, target *production* (ikke preview). Værdien er ikke læst.
* **Render** (`dialogbot-api-staging`): kan **ikke** verificeres – Render-værktøjerne viser ikke miljøvariablernes navne, og
  appen logger intet om variablen. (Ejeren har tidligere oplyst at den er sat.)

## 4. Oprettet / slettet / omkostning

| Ressource | Status |
|---|---|
| Render Postgres `loadtest-2026-11-13-db` (`dpg-dbrelkjbc2fs73cs4vg0-a`, basic_1gb, Frankfurt, oprettet 13/11 10:47 UTC) | **Ikke slettet – kan ikke slettes med værktøjerne.** Tom (ingen tabeller, ingen IP-adgang). **Ejeren skal slette den:** https://dashboard.render.com/d/dpg-dbrelkjbc2fs73cs4vg0-a → *Settings* → *Delete Database*. Pris ~19 USD/md ≈ 0,026 USD/t ≈ 0,63 USD/døgn indtil den slettes. |
| Lokal database `loadtest_local`, lokal API/worker, git-worktree | Oprettet og slettet igen. |
| Supabase, Vercel | Intet oprettet eller ændret. |

Samlet omkostning: kun Render-databasen, ca. 0,03 USD pr. time fra 10:47 UTC til ejeren sletter den.
