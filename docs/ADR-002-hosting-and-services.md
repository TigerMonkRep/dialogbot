# ADR-002 — Hosting, frontend-auth og services

Dato: 25. september 2026. Status: vedtaget for milepæl A.

## Kontekst

Brugeren arbejder online (GitHub, Vercel, Supabase) og ønsker ikke lokal installation som forudsætning. Backenden (FastAPI + varig worker) findes og er testet. Der skal være én loginløsning.

## Beslutninger

1. **Render til API og worker, Vercel til Next.js, Supabase til PostgreSQL/Storage.** Workeren er en uendelig proces med leases og backoff; den hører ikke hjemme i en tidsbegrænset function. Begge Render-tjenester deler stagingdatabasen med adskilte, små connection pools (`DB_POOL_SIZE`). Blueprint: `infra/render.yaml`.
2. **Eget schema på Supabase.** Applikationstabellerne ligger i schema `dialogbot`, som holdes ude af Supabases Data API (PostgREST). Migrationer kører med rollen `dialogbot_migrate` som eksplicit pre-deploy-trin; runtime bruger `dialogbot_app` uden DDL-rettigheder (`infra/supabase-roles.sql`). Alembic sætter `version_table_schema`. Supabases egne schemas (`auth`, `storage`, …) berøres ikke. RLS er ikke indført: backendens bruger-ID'er er ikke `auth.uid()`, og en politik baseret på den antagelse ville være uvirksom; adskillelsen ligger i applikationslaget (testet) og i, at kun backendens rolle kan nå schemaet.
3. **Login bevares (etape 1).** Ingen Supabase Auth. Frontenden bruger et **BFF-mønster på samme origin**: `POST /api/auth/login` (Next route handler) veksler credentials til backendens sessionstoken og lægger det i en `httpOnly; Secure; SameSite=Lax`-cookie. Al browsertrafik til API'et går via `/api/backend/*`, som tilføjer Bearer-headeren server-side. Tokenet er aldrig læsbart i JavaScript og aldrig i `localStorage`. CSRF: SameSite=Lax + obligatorisk `x-requested-with: dialogbot` på alle ikke-GET-kald (afvist med 403 uden). CORS er derfor ikke nødvendigt; API'et kaldes kun server-til-server. Personaliserede sider sendes med `Cache-Control: no-store, private` (proxy + `vercel.json`), så intet havner i fælles CDN-cache.
4. **Session-udløb i UI.** `src/proxy.ts` er kun et optimistisk gate (redirect til `/login?next=`); autorisation sker i backenden pr. request. Et 401 fra BFF sender browseren til `/login?expired=1`.
5. **Staging-profil.** `APP_ENV=staging` har prod's hærdning (SECRET_KEY, ingen dev-værktøjer) men tillader `EMAIL_ADAPTER=simulated`, indtil Resend er verificeret. `prod` afviser simuleret mail.
6. **Mail via Resend** med `Idempotency-Key = outbox_event_id`; status `sent` betyder "accepteret af udbyder". Leveringsstatus følger webhooks (milepæl B).
7. **Frontendstruktur.** `web/` (Root Directory på Vercel). Designtokens i `globals.css` (`@theme`). Fælles komponenter i `src/components/ui.tsx`. Server components henter data med `backend()`; client components muterer via `api()`. Routes følger kravmatricen (`/signup`, `/login`, `/verify-email`, `/password/*`, `/invite/:token`, `/onboarding/*`, `/app/*`).

## Konsekvenser

- Previews på Vercel peger på staging-API'et via `API_BASE_URL` (Preview-miljø); produktion får egen værdi. Ingen `NEXT_PUBLIC_`-hemmeligheder.
- Et frontend-preview kan ikke fungere, før Render-API'et findes; GitHub er første forudsætning for begge.
- Browserkontrol (390/1440 px, tastatur, fokus) udestår: der var ingen browser i udviklingsmiljøet. Det er registreret som åben rest i `docs/implementation-progress.md`.
