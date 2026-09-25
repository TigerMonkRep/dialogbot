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

Der findes ingen `NEXT_PUBLIC_*` hemmeligheder. Browseren kender kun sit eget origin; sessionen ligger i cookien `db_session` (httpOnly, Secure, SameSite=Lax), det valgte arbejdsrum i `db_ws`.

## Senere milepæle (navne reserveret, ikke læst af koden endnu)

`AI_PROVIDER`, `AI_MODEL_ID`, `ANTHROPIC_API_KEY`, `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_MESSAGING_SERVICE_SID`, `RESEND_WEBHOOK_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` (eneste offentlige), `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID`/`MS_CLIENT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (kun backend, kun til Storage-adapteren), `STORAGE_BUCKET_SOURCES`, `STORAGE_BUCKET_EXPORTS`.
