# Implementeringsfremdrift

Vedligeholdes ved hvert checkpoint. Statusord: implementeret · testet lokalt/CI · deployet · eksternt verificeret.

## Checkpoint 4 — 25. september 2026 (milepæl A: design-fidelitet mod Stitch)

**Gren/PR:** `claude/cool-wozniak-ho00tr` → https://github.com/TigerMonkRep/dialogbot/pull/2 (draft). CI (backend + web) grøn på `d2edbb7`.
**Referencer:** Stitch-eksporten (44 skærme, desktop + mobil) ligger i `design-reference/latest/stitch_dialogbot/`; skærmoversigt og DESIGN.md også hentet via Stitch MCP (`design-reference/stitch/`).
**Metode:** `design-reference/tools/stitch-render.mjs` renderer hver Stitch-`code.html` offline (Tailwind v3 kompileret fra skærmens egen config, lokale fonte, faner via `STITCH_EVAL`). `compare.mjs` logger ind i appen og laver side-om-side-billeder ved 1440 px (desktop-reference) og 390 px (mobil-reference). Kørt mod lokal API + PostgreSQL med seed-data.

| Skærm | Rute | Desktop 1440 | Mobil 390 | Bemærkninger |
|---|---|---|---|---|
| App-skal (guide) | /app/setup, /onboarding/* | matchet (G01-header, footer) | matchet (header, bundnav, Mere-ark) | "Aktiv AI" kun når `ai.conversation` er `available` |
| App-skal (admin) | /app/knowledge, /app/settings/*, /app/not-yet | matchet (K01-sidebjælke + topheader) | matchet (header, 5-punkts bundnav) | Stitch bruger topnav i opsætning og sidebjælke i drift – fulgt pr. skærm |
| G01–G05 | /app/setup | matchet | matchet | Persona (O05), AI-forslag og H01-support vist som ikke tilgængelige |
| A06/O01/O02 | /onboarding/business, /onboarding/workspace | matchet | matchet | O02 viser rigtig manuel viden; ingen "konfidens"-tal eller udtræk |
| O03/O04 | /onboarding/goals, /onboarding/languages | kortdesign fra G01 | kortdesign fra G01 | Ingen selvstændig Stitch-skærm |
| K01–K05, R05/R06 | /app/knowledge?tab=… | matchet (alle faner) | matchet (K01) | Strukturerede formularer i stedet for JSON; K05 sammenligning; K01/R05/R06 ærlige tomtilstande |
| A01–A05 | /signup, /login, /verify-email, /password/*, /invite/[token] | centreret kolonne | matchet (A04) | Kun mobilreference findes i Stitch |

**Funktionelt verificeret i browser (lokalt):** login; O01 "Gem" og "Gem og fortsæt" (gemmer før navigation); K03 prisændring → kladde → K05-sammenligning → godkend → ny aktiv pris.

**Ikke gjort endnu:** S08 profil, S09 aktivitetslog, G03-wrapper, P01 forside, S02 team i nyt design; Playwright-rejser i CI (blueprint §9.1 findes ikke i repoet); staging-screenshots (netværkspolitik blokerer stadig `*.vercel.app`/`*.onrender.com` i denne container).

**Præcis næste handling:** S08/S09/S02 i admin-skal → Playwright-suite i CI (lokal API + PostgreSQL, 390/1440-screenshots som artefakter, tastatur/fokus) → merge PR #2 → kontrollér staging.

## Checkpoint 3 — 25. september 2026 (overtagelse, milepæl A-design)

**Baseline genkontrolleret:** `main` = `cb79a99` (Stitch-commit er på main). 26/26 pytest mod lokal PostgreSQL 16, `npm run build` grøn (22 ruter). Render `dialogbot-api-staging` live på `cb79a99` (deploy `dep-dar7koe7bikc73auval0`, via Render-API). `/health/ready` og Vercel-URL kunne **ikke** kaldes direkte: sessionens netværkspolitik blokerer `*.onrender.com` og `*.vercel.app`, og Vercel-forbindelsen har ikke adgang til projektet.

**Fundet og rettet (browserkontrolleret lokalt, Chromium 1440/390 px):**

| Fejl | Årsag | Rettelse |
|---|---|---|
| Hele designsystemet virkede ikke på staging: ingen farver, spacing, typografi eller `lg:`-layout | Kommentaren i `globals.css` indeholdt `stitch_dialogbot/*/code.html`; `*/` lukkede kommentaren, så `@theme`-blokken blev en ugyldig regel og droppet af Next' CSS-pipeline (CSS 22 KB → 36 KB efter rettelse) | Kommentar rettet |
| Ikoner vist som tekst (`check_circle`, `schedule`) og systemfont i stedet for Inter/Manrope | Fonte hentet fra Google Fonts ved runtime | Self-hostet via `material-symbols`, `@fontsource-variable/inter`, `@fontsource-variable/manrope` i `@layer base`; ingen runtime-kald til Google (også GDPR-venligere) |

**Ikke gjort / blokeringer:**
- **Designreferencerne findes ikke i repoet eller containeren:** `design-reference/latest/stitch_dialogbot/` (44 HTML), `legacy-html/` (128 HTML), `Dialogbot-Backend-Blueprint.md`, `canonical-requirements.json`, `canonical-demo-data.json`, `implementation-backlog.csv`, `Dialogbot-Claude-Full-Platform-Prompt.md`. Uden dem kan side-for-side-sammenligning (§3) og de otte brugerrejser (blueprint §9.1) ikke udføres.
- Kendt afvigelse set lokalt: mobilheaderen (390 px) klipper ikonerne til højre.

**Præcis næste handling:**
1. **Bruger:** læg afleveringspakken i repoet (fx `design-reference/` og `docs/handoff/`) og tillad `dialogbot-api-staging.onrender.com` og `dialogbot-sepia.vercel.app` i miljøets netværksindstillinger.
2. **Claude:** efter merge — screenshot staging mod Stitch-referencer ved 1440/390 px, ret afvigelser, byg S08/S09/G03/G04, tilføj Playwright-CI.

## Checkpoint 2 — 25. september 2026 (milepæl A, delvist)

**Commits:** `f24c75f` (etape 1) → `60726df` (milepæl A: frontend, infra, docs).
**GitHub:** https://github.com/TigerMonkRep/dialogbot — `main` på `c874941`, fuld historik (eksternt verificeret via `git ls-remote`).
**CI:** GitHub Actions run #1 grøn for både `CI` (48 s) og `Web` (35 s) på `c874941`.
**Supabase (eksternt verificeret):** projekt `dialogbot-staging`, ref `zofdupmpcokvcvstsozm`, eu-central-1, 10 USD/md. bekræftet af bruger. Schema `dialogbot` med roller `dialogbot_migrate` (ejer) og `dialogbot_app` (DML, ingen DDL). Alembic `94af55693109` anvendt som offline-SQL via forbindelsen: 19 tabeller i `dialogbot`, 0 i `public`, `anon`/`authenticated` uden adgang, security-advisor 0 fund. Adgangskoder udleveret én gang i chat (ikke i repo). Udestår i dashboard: bekræft at `dialogbot` ikke er i *Exposed schemas*.
**Deploy:** Render og Vercel ikke oprettet endnu (forbindelser ikke tilkoblet).

### Færdigt siden etape 1

| Del | Status | Bevis |
|---|---|---|
| Baseline verificeret | testet lokalt | 26/26 pytest mod PostgreSQL 16.15, ruff ren, `alembic check` ren, låste versioner stemmer |
| Next.js-frontend `web/` (Next 16.3, TS, Tailwind 4, designsystem) | implementeret, build verificeret | `npm run build` → 21 ruter; `tsc --noEmit` ren |
| Ruter: `/`, `/signup`, `/login`, `/verify-email`, `/password/forgot`, `/password/reset`, `/invite/[token]`, `/onboarding/{workspace,business,goals,languages}`, `/app/setup`, `/app/knowledge`, `/app/settings/team`, `/app/settings/business` | implementeret | HTTP-gennemløb mod live API+worker: login-cookie, redirect for uautentificeret, plan/viden/team server-renderet med rigtige data, CSRF-afvisning, tjek-kørsel via proxy, logout |
| BFF-auth (httpOnly-cookie, same-origin proxy, CSRF-header, no-store) | implementeret, testet på HTTP-niveau | `docs/ADR-002-hosting-and-services.md` |
| Backend: `APP_ENV=staging`, `DB_SCHEMA`, pool-størrelser, Resend-adapter | implementeret; schema-migration testet lokalt | 19 tabeller i schema `dialogbot`; Resend **ikke eksternt verificeret** |
| `infra/render.yaml`, `infra/supabase-roles.sql`, `web/vercel.json`, `.github/workflows/web.yml` | implementeret | — |
| `docs/services-setup.md`, `docs/environment-variables.md`, `docs/ADR-002` | skrevet | — |

### Ikke gjort / blokeringer

- **Render/Vercel** — ikke tilkoblet; Render-blueprint klar. Vercel-forbindelse set aktiv, men frontend-preview er meningsløs uden API.
- **Browserkontrol** (390/1440 px, tastatur, fokus, layout mod Stitch-referencer) — ikke udført; ingen browser i miljøet.
- Frontend mangler: P02–P09 (offentlige sider), S08 profilside, S09 aktivitetsvisning, G03-wrapper med eksempler, G04-drawer, K02 kilder. Disse er ikke skjult: `/app/setup` viser ikke-implementerede trin som "Ikke tilgængelig".
- Budget med to scenarier — udestår, indtil priser slås op ved tilkobling.
- Resend-leveringswebhooks, Anthropic/Vapi/Twilio/Stripe/kalender — milepæl B–D.

### Præcis næste handling

1. **Bruger:** tilkobl Render-forbindelsen (eller opret Blueprint manuelt fra `infra/render.yaml`); indsæt `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `DB_SCHEMA=dialogbot`, `FRONTEND_BASE_URL`, `PUBLIC_BASE_URL`, `EMAIL_FROM` som secrets. Hent hosts fra Supabase Connect (session pooler til runtime, direct til migration).
2. **Claude:** verificér `/health/ready` på Render → Vercel-import (Root `web`, `API_BASE_URL`) → gennemfør konto→viden→plan på preview-URL og notér links her.
3. **Uafhængigt af adgang:** fortsæt milepæl A-frontend (P02–P09, S08, S09) og forbered Resend-webhook + Anthropic-adapter (milepæl B).
