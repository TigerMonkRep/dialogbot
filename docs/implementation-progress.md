# Implementeringsfremdrift

Vedligeholdes ved hvert checkpoint. Statusord: implementeret · testet lokalt/CI · deployet · eksternt verificeret.

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
