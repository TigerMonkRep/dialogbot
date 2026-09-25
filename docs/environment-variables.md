# Miljøvariabler — autoritativt manifest

Ét navn pr. hemmelighed. Render, Vercel, CI og lokal `.env` bruger disse navne. Ingen værdier her.

## Backend (Render `dialogbot-api-*` og `dialogbot-worker-*`, lokal `.env`)

| Variabel | Påkrævet | Modtager | Hentes fra | Bemærkning |
|---|---|---|---|---|
| `APP_ENV` | ja | API, worker | — | `dev` / `test` / `staging` / `prod`. staging+prod: kræver `SECRET_KEY`, forbyder dev-værktøjer. prod forbyder desuden `EMAIL_ADAPTER=simulated`. |
| `DATABASE_URL` | ja | API, worker, CI (test-DB) | Supabase → Connect → session pooler/direct, rolle `dialogbot_app` | `postgresql+psycopg://…`. Begrænset runtime-rolle. |
| `MIGRATION_DATABASE_URL` | staging/prod | Render pre-deploy (API) | Supabase → Connect → direct, rolle `dialogbot_migrate` | Kun til `alembic upgrade head`. Aldrig i worker. |
| `DB_SCHEMA` | Supabase | API, worker, migration | — | `dialogbot`. Lokalt/CI: udelad (= `public`). |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | nej | API, worker | — | Standard 5/5. Worker kan sættes til 2/2. |
| `SECRET_KEY` | staging/prod | API, worker | Render `generateValue` (API) → kopiér samme værdi til worker | ≥ 32 tegn. |
| `ENABLE_DEV_TOOLS` | nej | API | — | `true` kun i dev/test. Åbner `/api/v1/dev/*` (simuleret postkasse). |
| `AUTH_PROVIDER` | nej | API | — | `local`. `external` er reserveret og fejler lukket. |
| `SESSION_TTL_HOURS`, `INVITATION_TTL_HOURS`, `RESET_TTL_MINUTES`, `VERIFICATION_TTL_HOURS` | nej | API | — | Standard 336 / 72 / 60 / 48. |
| `EMAIL_ADAPTER` | ja | API, worker | — | `simulated` (dev/test/staging) eller `resend`. |
| `RESEND_API_KEY` | ved resend | worker (API kun hvis den sender synkront – det gør den ikke) | Resend → API Keys | Staging- og prod-nøgle adskilt. |
| `RESEND_WEBHOOK_SECRET` | ved resend | API | Resend → Webhooks → endpoint → *Signing secret* (`whsec_…`) | Uden den svarer `POST /api/v1/webhooks/resend` 503. Én pr. miljø. |
| `AI_PROVIDER` | nej | API | — | `none` (standard: AI-endpoints svarer 501), `anthropic`, eller `fake` (testdobbelt, kun dev/test – afvises ellers ved opstart). |
| `AI_MODEL_ID` | nej | API | Anthropic → Models | Standard `claude-opus-5`. Logges pr. kald i `ai_usage`. |
| `ANTHROPIC_API_KEY` | ved anthropic | API | Anthropic Console → API Keys (sæt månedligt forbrugsloft) | Uden nøgle nægter processen at starte med `AI_PROVIDER=anthropic`. |
| `AI_EFFORT` | nej | API | — | `low` / `medium` (standard) / `high`. |
| `AI_MAX_OUTPUT_TOKENS` | nej | API | — | Standard 2048 (inkl. tænkning). |
| `AI_SERVER_FALLBACKS` | nej | API | — | `true` (standard): Anthropics server-side fallback ved politik-afvisning (`fallbacks: "default"`). Sæt `false`, hvis `AI_MODEL_ID` ikke har en standard-fallback. |
| `WEBCHAT_DAILY_REPLY_LIMIT` | nej | API | — | Standard 300. Højeste antal AI-svar pr. arbejdsrum pr. døgn i web-widgetten (udgiftsværn). Derudover: 20 beskeder pr. samtale, 60 nye samtaler i timen pr. widget. |
| `VAPI_SERVER_SECRET` | ved telefoni | API | Vælges af jer; samme værdi som Bearer-legitimationen på nummerets Server URL i Vapi | Uden den svarer `POST /api/v1/webhooks/vapi` 503, og `telephony.inbound` er `not_implemented`. |
| `VAPI_MODEL_PROVIDER` / `VAPI_MODEL` | nej | API | — | Model, som Vapi bruger i samtalen. Standard `anthropic` / `AI_MODEL_ID`. Verificér, at Vapi understøtter modellen. |
| `VAPI_VOICE_JSON` / `VAPI_TRANSCRIBER_JSON` | nej | API | Vapi-dashboardet | Valgfri JSON-objekter, der sendes uændret som `voice`/`transcriber` (fx en dansk stemme og dansk transskribering). |
| `EMAIL_FROM` | ved resend | worker | Verificeret afsenderdomæne i Resend | `Dialogbot <noreply@mail.<domæne>>` |
| `PUBLIC_BASE_URL` | ja | API | Render-URL | Bruges i OpenAPI/links. |
| `FRONTEND_BASE_URL` | ja | API, worker | Vercel-URL | Links i mails (verificering, reset, invitation). |
| `WORKER_POLL_SECONDS`, `WORKER_LEASE_SECONDS`, `WORKER_MAX_ATTEMPTS` | nej | worker | — | 1 / 60 / 5. |
| `LOG_LEVEL` | nej | API, worker | — | `INFO`. |
| `SEED_DEMO_PASSWORD` | nej | manuel kørsel (kun dev/staging) | — | Seed nægter `prod`. |
| `TEST_DATABASE_URL` | CI/lokal test | pytest | — | Separat database; skemaet droppes ved hver kørsel. |

## Frontend (Vercel-projekt med Root Directory `web`)

| Variabel | Påkrævet | Miljø | Bemærkning |
|---|---|---|---|
| `API_BASE_URL` | ja | Production, Preview | Render-API'ets URL (staging til Preview, prod til Production). **Server-only** – ingen `NEXT_PUBLIC_`-variant findes eller må oprettes. |
| `PREVIEW_GATE` | nej | Production, Preview | — | **Slået til som standard**: forsiden `/` og `/signup` ligger bag den midlertidige adgangsside `/preview` (P00), indtil platformen er klar. `off` åbner siderne (fx lokalt). Indloggede brugere og invitationslinks (`/signup?next=/invite/…`) slipper igennem. |
| `PREVIEW_ACCESS_CODES` | ved gate | samme | Vælges af jer | Kommaseparerede invitationskoder, mindst 8 tegn hver (kortere ignoreres). Store/små bogstaver er ligegyldige. **Server-only.** |
| `PREVIEW_COOKIE_SECRET` | ved gate | samme | Tilfældig streng ≥ 32 tegn | Signerer adgangscookien `db_preview` (httpOnly, 30 dage). Udskiftes den, skal alle indtaste en kode igen. Mangler den, låser ingen kode op (fejler lukket). |

Der findes ingen `NEXT_PUBLIC_*` hemmeligheder. Browseren kender kun sit eget origin; sessionen ligger i cookien `db_session` (httpOnly, Secure, SameSite=Lax), det valgte arbejdsrum i `db_ws`.

## Senere milepæle (navne reserveret, ikke læst af koden endnu)

`AI_PROVIDER`, `AI_MODEL_ID`, `ANTHROPIC_API_KEY`, `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_MESSAGING_SERVICE_SID`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` (eneste offentlige), `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID`/`MS_CLIENT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (kun backend, kun til Storage-adapteren), `STORAGE_BUCKET_SOURCES`, `STORAGE_BUCKET_EXPORTS`.
