# 1. Opsætning og agenter – opgørelse og før/efter

Run-id `2026-11-12-platform-audit` · kandidat `origin/main` 14edd47 (+ denne branchs rettelser) · udført af qa-lead.

## Hvad der findes (discovery 12/11)

| Område | Fundet | Vurdering |
|---|---|---|
| Projektinstruktioner | `README.md`, `web/AGENTS.md`/`web/CLAUDE.md` (Next 16-regel), ingen rod-CLAUDE.md | Tilstrækkeligt; detaljer ligger i `qa/README.md` |
| Agenter `.claude/agents/` | 14: qa-lead, verifier, fix-engineer, e2e-erhverv, e2e-privat, voice-qa, api-contract-qa, billing-qa, integrations-qa, security-privacy, i18n-a11y-qa + designrådgivere ui-ux-engineer, art-director, designer | Gyldig frontmatter (name/description/tools/model) for Claude Code 2.1.322. Ingen `.claude/rules`, `skills`, `commands`, `settings.json` i projektet |
| QA-protokol | `qa/README.md`, `qa/ledger.md`, `qa/scenarios.csv` (160 Erhverv/fælles), `qa/privat/scenarios.csv` (273 Privat), 252 fundfiler `qa/findings/F-*.md`, `qa/evidence/`, `qa/reports/2026-11-10-run.md` | Ét system – genbrugt, ikke erstattet |
| Backend-tests | pytest mod rigtig PostgreSQL, ~100 testfiler + 60 i `tests/qa/` | CI: 2408 passed, 35 skipped, 48 xfailed (14edd47) |
| Browser-tests | Playwright 132 specs: `web/e2e/*.spec.ts` (journeys = deploy-gate), `web/e2e/qa/**` (katalog, 4 shards, `continue-on-error`), `web/e2e/privat/**` | ~420 tests springes over i CI (se F-AUD26-03-CI) |
| CI | `ci.yml` (test, voice-services, browser-worker), `e2e.yml` (journeys, privat, qa-catalog 1–4), `web.yml`, `deploy-check.yml` (schema-head hver time mod produktion, read-only) | Alt grønt på 14edd47 |
| Migrationer | 81 Alembic-revisioner, `alembic check` i CI | Produktion på head 0c1d5e7a9b3f = main |
| Integrationer | Fake-adaptere for AI, TTS, telefoni (Vapi/Twilio), connectors, e-mail (simulated), Stripe (fake/test) | Mock-beviser ≠ udbyderbeviser (se rapport §Integrationer) |

## Kendt begrænsning i denne session
qa-lead kørte som subagent **uden Agent-værktøj**. `SendMessage` til `verifier` svarede «No agent named 'verifier' is reachable» (12/11 kl. ~15:10 UTC). Specialisterne kunne derfor ikke startes. Audit-passene (security, API, CI/infra, domæne) er udført af qa-lead med eksplicitte roller, og rettelsen F-AUD26-01 er skrevet af qa-lead. Det er **ikke** uafhængig verifikation; den gate står som BLOCKED, indtil hovedsessionen starter `verifier` (subagent_type: verifier) på PR'en.

## Ændringer i agenterne (før → efter)

| Agent | Før | Efter | Hvorfor |
|---|---|---|---|
| i18n-a11y-qa | «Travelpayouts Drive in <head>» godkendt | Drive fjernet (#203); ethvert Travelpayouts-/Drive-script på Erhverv = S1; beslutning B (kun /privat bag flag) er ikke en defekt. WCAG 2.2 AA; axe er et gulv; skippede specs = NOT TESTED | Forældet godkendelse; briefens §6D |
| qa-lead | Ingen regel for spawn/uafhængighed, intet audit-format | Spawn via Agent-værktøjet med subagent_type; uden Agent-værktøj: BLOCKED-gate, ikke «uafhængig»; audit-leverancer i `docs/qa/<run-id>/`; resultatord og mapping; CI-skip-tælling; domæne-pass; §10-blok | Gamle fejl (verifier ikke nåbar); briefens §3–§4, §10 |
| verifier | Kun fund-for-fund | + kandidat-SHA, primær evidens, skipped/xfail/retry ≠ pass, sig til hvis ikke separat agent | Briefens §8 |
| api-contract-qa | Ingen drift/ydelse | + rolle «performance/operations reviewer»: worker-genstart, udbyderfejl, migration på data, latens, schema-head; backup/restore = BLOCKED uden Fürsters adgang | Briefens §4/§6F – ingen ny agent nødvendig |
| security-privacy | Ingen reference/nye døre | + OWASP ASVS 5.0 (L2 app, L1 offentligt); /demo-call 24/7-misbrug, cold outreach (unsubscribe-signatur, webhook-secret, OUTREACH_MODE), filimport | Dagens merges #196/#198/#204 |
| voice-qa | – | + salgsopkald 24/7 (beslutning), gamle `scheduled`-rækker, outreach må aldrig bruge stemme/SMS | #198, #204 |

Ansvar fra briefens tabel → eksisterende agenter: koordinator = qa-lead; produkt/domæne = qa-lead (domæne-pass) + ui-ux-engineer; backend/data/integration = api-contract-qa + integrations-qa + billing-qa; frontend/UX/a11y = e2e-erhverv, e2e-privat, i18n-a11y-qa; testautomation = specialisterne (kun tests); security = security-privacy; ydelse/drift = api-contract-qa (ny sektion) + i18n-a11y-qa (web-ydelse); implementering = fix-engineer; uafhængig verifikation = verifier. Ingen nye agenter – overlap undgås.

## Verifikation af konfigurationen
- Frontmatter-felterne er de samme som før (gyldige i 2.1.322); ingen nye felter tilføjet.
- `claude agents --json` lister kun kørende baggrundsagenter (tom liste) – ikke definitioner, så det beviser ikke opdagelse.
- En reel, afgrænset opgave til en specialist kunne ikke køres herfra (intet Agent-værktøj). **Krævet næste skridt:** hovedsessionen starter `verifier` med opgaven i `README.md` §«Til verifier».
