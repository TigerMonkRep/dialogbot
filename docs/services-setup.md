# Services og opsætning — hvad der er klar, og hvad du skal gøre

Dato: 25. september 2026. Gælder milepæl A (GitHub, Supabase, Render, Vercel). AI/voice/betaling tilkobles først, når integrationerne er konkrete (milepæl B–D) — se afsnittet "Senere" nederst.

Statusord i dette dokument: **klar i repo** (kode/konfiguration findes og er testet lokalt), **kræver din handling**, **ikke verificeret eksternt** (kan først bekræftes, når ressourcen findes).

## 0. GitHub — GJORT (25/9): https://github.com/TigerMonkRep/dialogbot, CI grøn

**Hvorfor:** Render og Vercel deployer fra et GitHub-repository. Uden det findes ingen previews, ingen CI-kørsel og ingen staging.

**Situationen i dette miljø:** Der er ingen GitHub-forbindelse tilgængelig i denne session (kun Vercel, Render og Supabase findes som forbindelser). Jeg kan derfor ikke oprette repositoriet eller pushe. Jeg beder dig ikke om en token i chatten.

**Din handling (5 minutter, ingen manuel kopiering af filer):**

1. Opret et tomt privat repository på <https://github.com/new> med navnet `dialogbot` (uden README/licens/.gitignore).
2. Hent `dialogbot.bundle` fra afleveringen (fuld git-historik, 2 commits) og kør lokalt — eller i GitHub Codespaces, hvis du ikke vil køre noget på din computer:
   ```bash
   git clone dialogbot.bundle dialogbot && cd dialogbot
   git remote set-url origin https://github.com/<din-konto>/dialogbot.git
   git push -u origin main
   ```
3. Bekræft på GitHub, at commit `60726df` findes, og at Actions kører to workflows: **CI** (backend mod PostgreSQL) og **Web** (Next.js typecheck + build).

Alternativ uden lokal git: åbn Codespaces på det tomme repo, upload bundlen, kør de samme tre kommandoer. Bevis for succes: grønne checks på GitHub → `docs/implementation-progress.md` opdateres med URL og run-id.

## 1. Supabase — database (staging)

| | |
|---|---|
| Hvorfor / hvornår | PostgreSQL til API og worker. Første stagingmiljø. |
| Dashboard | <https://supabase.com/dashboard> · [SQLAlchemy-vejledning](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT) · [Data API-sikkerhed](https://supabase.com/docs/guides/api/securing-your-api) |
| Projekt | **OPRETTET 25/9:** `dialogbot-staging`, ref `zofdupmpcokvcvstsozm`, eu-central-1, 10 USD/md. Schema, roller og Alembic-head anvendt og verificeret. Produktion oprettes senere som separat projekt. |
| Klar i repo | `infra/supabase-roles.sql` (schema `dialogbot`, migrationsrolle `dialogbot_migrate`, runtime-rolle `dialogbot_app`); backend understøtter `DB_SCHEMA`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`; Alembic migrerer ind i schemaet (verificeret lokalt: 19 tabeller i `dialogbot`, 0 i `public`). |
| Din handling | (a) Tilkobl Supabase-forbindelsen, når kortet vises nedenfor i chatten, så jeg kan oprette projektet og køre SQL — **eller** opret projektet selv og kør `infra/supabase-roles.sql` i SQL Editor med egne adgangskoder. (b) Settings → API → *Exposed schemas*: sørg for at `dialogbot` **ikke** er med; overvej at deaktivere Data API helt, da al forretningsdata går gennem FastAPI. (c) Kopiér forbindelsesstrenge fra **Connect**-dialogen. |
| Variabler | `MIGRATION_DATABASE_URL` = direct connection som `dialogbot_migrate` (Render API, kun pre-deploy). `DATABASE_URL` = session pooler eller direct som `dialogbot_app` (Render API + worker). Format: `postgresql+psycopg://dialogbot_app:<pw>@<host>:<port>/postgres`. `DB_SCHEMA=dialogbot`. |
| Test / bevis | Render pre-deploy kører `alembic upgrade head`; `/health/ready` svarer `{"status":"ok","migration":"94af55693109"}`; `python -m scripts.seed` mod staging (kun staging); `pytest` med `TEST_DATABASE_URL` mod en separat test-database i samme projekt. Worker: kø og genstart afprøves via `/api/v1/dev/outbox` **kun i dev**; i staging via Render-logs. |
| Udgift | Free-tier til staging (pause ved inaktivitet); Pro fra 25 USD/md. ved produktion. Priser skal slås op ved købstidspunktet. |
| Ikke verificeret eksternt | Pooler-kompatibilitet med `options=-csearch_path` (kendt begrænsning på transaction pooler; derfor anbefales session pooler eller direct), TLS. Testes fra Render ved første deploy. |

## 2. Render — API og worker (staging)

| | |
|---|---|
| Hvorfor / hvornår | Kontinuerlig Python-runtime for FastAPI og den varige outbox-worker. Sammen med databasen. |
| Dashboard | <https://dashboard.render.com/> · [Blueprints](https://render.com/docs/infrastructure-as-code) · [Background workers](https://render.com/docs/background-workers) |
| Klar i repo | `infra/render.yaml`: `dialogbot-api-staging` (web, `/health/ready`, migration som pre-deploy) og `dialogbot-worker-staging` (worker). Region Frankfurt, plan Starter. |
| Din handling | Efter GitHub: Dashboard → Blueprints → New Blueprint Instance → vælg repo → `infra/render.yaml`. Udfyld secrets (`DATABASE_URL`, `MIGRATION_DATABASE_URL`, `PUBLIC_BASE_URL`, `FRONTEND_BASE_URL`, `EMAIL_FROM`; `RESEND_API_KEY` først når Resend er sat op). Sæt `EMAIL_ADAPTER=simulated` i staging, indtil Resend er verificeret (skift til `resend`). Alternativt: tilkobl Render-forbindelsen, så opretter jeg tjenesterne. |
| Test / bevis | Deploy grøn + `GET https://dialogbot-api-staging.onrender.com/health/ready` = ok. Worker: opret en invitation via API → Render-log viser `outbox.processed`. Genstart worker midt i et job: jobbet genoptages efter lease (60 s) uden dobbelt levering (samme test som `test_worker_outbox_retry_and_no_duplicate_delivery`, nu mod staging). |
| Udgift | 2 × Starter ≈ 7 USD/md. hver (listepris; verificér). Free-plan sover og egner sig ikke til worker. |

## 3. Vercel — Next.js-frontend

| | |
|---|---|
| Hvorfor / hvornår | Kundeapp, onboarding og (senere) offentlig site/widget. Første browserforløb. |
| Dashboard | <https://vercel.com/dashboard> · [Hobby-vilkår](https://vercel.com/docs/plans/hobby) |
| Klar i repo | `web/` (Next.js 16, TypeScript, Tailwind 4, Manrope/#e7fef9/#164e43/#d8ee86), `web/vercel.json` (region fra1, `no-store` på personaliserede ruter). Auth via same-origin BFF: session i httpOnly-cookie, `/api/backend/*` proxy, CSRF-header på mutationer. Build verificeret lokalt (21 ruter). |
| Din handling | Import repo → **Root Directory = `web`** → Environment Variable `API_BASE_URL` = Render-API'ets URL (Production + Preview; **ikke** `NEXT_PUBLIC_`). Deploy. Planvalg: Hobby er til ikke-kommerciel brug; kommerciel lancering kræver Pro (20 USD/bruger/md. listepris — verificér før køb). |
| Test / bevis | På preview-URL: signup → bekræft e-mail (i staging med simuleret mail: jeg læser linket via Render-log/DB, indtil Resend er klar) → arbejdsrum → virksomhed → mål → sprog → viden → godkend → plan. Cookie sættes `Secure; HttpOnly; SameSite=Lax`; POST uden `x-requested-with` afvises (403). Kontrol i browser ved 390/1440 px er **ikke udført** (ingen browser i dette miljø). |
| Bemærk | `FRONTEND_BASE_URL` i Render skal pege på Vercel-domænet, så links i mails rammer frontenden. |

## 4. Resend — systemmail (tidligt i milepæl B, men kan sættes op nu)

| | |
|---|---|
| Hvorfor | Verificering, reset, invitationer skal faktisk leveres i staging/produktion. |
| Dashboard | <https://resend.com/> · [Domæner](https://resend.com/docs/dashboard/domains/introduction) |
| Klar i repo | `ResendEmailAdapter` (`app/modules/integrations/email.py`) med `Idempotency-Key = outbox_event_id`; gemmer Resends id i `email_deliveries.provider_message_id`; status `sent` ≠ leveret. Leveringswebhook `POST /api/v1/webhooks/resend` (`app/modules/webhooks/`): Svix-signatur (verificeret mod officiel `svix`-testvektor), 5-minutters replay-vindue, idempotent på `svix-id`, `provider_status` bevæger sig kun fremad (sent → delivery_delayed → delivered → failed/bounced/complained). **Ikke verificeret eksternt** (ingen Resend-konto endnu). |
| Din handling | 1) Vælg afsenderdomæne (fx `mail.<dit-domæne>`); tilføj DNS-poster (SPF/DKIM/DMARC), som Resend viser for præcis dette domæne; opret API-nøgle med *sending access*. 2) Resend → Webhooks → *Add endpoint*: URL `https://dialogbot-api-staging.onrender.com/api/v1/webhooks/resend`, hændelser `email.sent`, `email.delivered`, `email.delivery_delayed`, `email.bounced`, `email.complained`, `email.failed`. 3) I Render (dialogbot-api-staging): `RESEND_WEBHOOK_SECRET` = endpointets *Signing secret*; i API **og** worker: `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_ADAPTER=resend`. Oplys en testmodtageradresse. Del aldrig nøglerne i chat. |
| Test / bevis | Verificeringsmail til testadressen → `email_deliveries.status=sent` med `provider_message_id` → webhook sætter `provider_status=delivered`; `webhook_events` har én række pr. `svix-id`. Resend-dashboardets "Send test event" skal give 200. |
| Udgift | Free: 3.000 mails/md. (listepris; verificér). |

## 5. Anthropic — AI-assistent (milepæl B)

| | |
|---|---|
| Hvorfor | Assistenten skal kunne svare ud fra den godkendte viden. |
| Dashboard | <https://console.anthropic.com/> · Settings → Limits (forbrugsloft) · API Keys |
| Klar i repo | `app/modules/ai/`: `AIProvider`-interface, `AnthropicProvider` (officiel `anthropic`-SDK, model fra `AI_MODEL_ID`, standard `claude-opus-5`; prompt caching; server-side refusal-fallback slået til). Prompten bygges **kun** af `active_knowledge` (godkendt, aktuel, ikke-arkiveret viden). Hvert kald logges i `ai_usage` med arbejdsrum, model (anmodet og faktisk), promptversion (`assistant-v1`), vidensrevision, tokens og estimeret pris. Endpoints: `POST /workspaces/{id}/assistant/preview` (staff+, intern test – ingen kundekanal) og `GET /workspaces/{id}/ai/usage` (admin+). `ai.conversation` forbliver `not_implemented`; UI viser ikke "Aktiv AI". **Ikke verificeret eksternt** (ingen nøgle endnu). |
| Din handling | 1) Opret en API-nøgle i en workspace kun til Dialogbot staging, og sæt et **månedligt forbrugsloft** (fx 20 USD) under Limits. 2) I Render (dialogbot-api-staging): `ANTHROPIC_API_KEY` = nøglen, derefter `AI_PROVIDER=anthropic`. Del aldrig nøglen i chat. |
| Test / bevis | Jeg kalder `/assistant/preview` på staging med et spørgsmål, der kan besvares af godkendt viden, og et der ikke kan → svar + `ai_usage`-række med `served_model`, tokens og `provider_request_id`. |
| Udgift | Betaling pr. token. Listepris for `claude-opus-5`: 5 USD / 1 mio. input- og 25 USD / 1 mio. output-tokens (verificér i Console). Et preview-kald med lille vidensbase ≈ 2–4k input + ≤ 2k output ≈ 0,02–0,07 USD. |

## 6. Vapi (+ Twilio) — telefoni (milepæl B)

| | |
|---|---|
| Hvorfor | Assistenten skal tage telefonen på jeres nummer. |
| Klar i repo | `POST /api/v1/webhooks/vapi` (Bearer eller `X-Vapi-Secret`, konstanttid): `assistant-request` → midlertidig assistent med systemprompt **kun** fra godkendt viden + telefonregler (kort, ingen formatering, AI-oplysning i hilsenen); `end-of-call-report` → opkald (`calls`), transskription som `phone`-samtale i indbakken, og hvis kunden sagde noget og nummeret er kendt: henvendelse + opgave "Ring tilbage" (idempotent pr. opkalds-id). Numre tilknyttes arbejdsrum under Indstillinger → Telefoni (E.164 + Vapis nummer-id). Tjekkene `telephony.test_call`/`telephony.forwarding` består først efter et rigtigt opkald. **Ikke verificeret eksternt.** |
| Din handling | 1) Opret Vapi-konto (evt. med jeres Twilio-konto til danske numre). 2) Opret/importér et nummer — **det koster penge; jeg køber intet uden at vise prisen og få jeres ja**. 3) Vælg en hemmelighed, læg den i Render som `VAPI_SERVER_SECRET`, og opret i Vapi en Bearer-legitimation med samme værdi på nummerets Server URL `https://dialogbot-api-staging.onrender.com/api/v1/webhooks/vapi`; lad nummerets assistent være tom. 4) Tilknyt nummeret i Dialogbot. 5) Viderestil jeres eksisterende nummer hos teleselskabet og ring et prøveopkald. 6) Vælg en dansk stemme pr. nummer under Indstillinger → Telefoni → "Stemme og talestil": find en dansk stemme i ElevenLabs' stemmebibliotek (ElevenLabs skal være forbundet i Vapi → Integrations), kopiér Voice ID, vælg model og evt. talestil. Transskribering er dansk som standard. |
| Test / bevis | Prøveopkald → samtale i indbakken med transskription, henvendelse + opgave, og tjekket "Prøveopkald" består i opsætningsguiden. |
| Udgift | Pr. minut hos Vapi (platform + model + stemme + transskribering) og nummer/minutter hos Twilio. Slå de aktuelle priser op, før I køber — jeg angiver dem ikke fra hukommelsen. |

## Senere (bed om input, når integrationen er konkret)

- **Google Cloud / Microsoft Entra** (milepæl C): redirect-URL'er og scopes leveres, når kalenderadapteren findes.
- **Stripe** (milepæl D): testmode først; webhook-secret; pris-/aftalemapping.

Budget med to scenarier (10 og 50 arbejdsrum) udarbejdes, når de faktiske forbrugspriser slås op ved tilkoblingen af hver udbyder — ikke fra hukommelsen.
