# Implementeringsfremdrift

Vedligeholdes ved hvert checkpoint. Statusord: implementeret · testet lokalt/CI · deployet · eksternt verificeret.

## Checkpoint 2 — 25. september 2026 (milepæl A, delvist)

**Commits:** `f24c75f` (etape 1) → `60726df` (milepæl A: frontend, infra, docs).
**GitHub:** ikke pushet — ingen GitHub-forbindelse i sessionen. Fuld historik ligger i `dialogbot.bundle` (se `docs/services-setup.md` §0).
**CI:** workflows `CI` (backend) og `Web` (frontend) er skrevet; samme trin er kørt lokalt. Ikke kørt på GitHub.
**Deploy:** intet deployet. Render-blueprint, Supabase-roller og Vercel-config er klar i repo.

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

- **GitHub-push** — blokeret (ingen forbindelse). Brugerhandling: se `docs/services-setup.md` §0.
- **Supabase/Render/Vercel** — forbindelser findes i katalog men er ikke tilkoblet; alle tre kræver desuden GitHub først (Render/Vercel).
- **Browserkontrol** (390/1440 px, tastatur, fokus, layout mod Stitch-referencer) — ikke udført; ingen browser i miljøet.
- Frontend mangler: P02–P09 (offentlige sider), S08 profilside, S09 aktivitetsvisning, G03-wrapper med eksempler, G04-drawer, K02 kilder. Disse er ikke skjult: `/app/setup` viser ikke-implementerede trin som "Ikke tilgængelig".
- Budget med to scenarier — udestår, indtil priser slås op ved tilkobling.
- Resend-leveringswebhooks, Anthropic/Vapi/Twilio/Stripe/kalender — milepæl B–D.

### Præcis næste handling

1. **Bruger:** opret tomt privat repo `dialogbot`, push `dialogbot.bundle` (3 kommandoer i `docs/services-setup.md` §0). Tilkobl Supabase-, Render- og Vercel-forbindelserne (kort i chatten).
2. **Claude, når GitHub findes:** verificér remote commit + grøn CI → opret `dialogbot-staging` på Supabase (EU Frankfurt), kør `infra/supabase-roles.sql`, fjern `dialogbot` fra exposed schemas → Render Blueprint fra `infra/render.yaml` med secrets → Vercel-import (Root `web`, `API_BASE_URL`) → gennemfør konto→viden→plan på preview-URL og notér links her.
3. **Uafhængigt af adgang:** fortsæt milepæl A-frontend (P02–P09, S08, S09) og forbered Resend-webhook + Anthropic-adapter (milepæl B).
