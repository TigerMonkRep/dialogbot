# Platform-audit 2026-11-12 – indeks, checkpoint og genkørsel

| Leverance (briefens §9) | Fil |
|---|---|
| 1. Opsætning/agenter før/efter | [inventory.md](inventory.md) |
| 2. Strategi, omfang, risici, gates | [strategy.md](strategy.md) |
| 3. Krav-/dækningsmatrix | [traceability.csv](traceability.csv) (genereret) |
| 4. Fundregister | [findings-register.csv](findings-register.csv) (genereret) + `qa/findings/F-AUD26-*.md` |
| 5. Kørselsmanifest | [execution-manifest.md](execution-manifest.md) |
| 6. Logs/evidens (uden hemmeligheder) | `qa/evidence/AUD26/` |
| 7. Endelig rapport + GO/NO-GO | `report.md` – **mangler i commit**: qa-lead-subagenten måtte ikke skrive rapportfilen; den fulde tekst er afleveret til hovedsessionen, som lægger den her |
| 8. Genkørsel + checkpoint | denne fil |
| 9. Ændringer | branch `qa/platform-audit-2026-11-12` (PR mod main, merges af Fürster) |

## Checkpoint (opdateres ved hvert stop)
- Sidst: 12/11, efter fuld pytest, journeys og read-only prod-checks. Branch skubbet.
- Færdigt: discovery, baseline, agentopgradering, audit-pass (security, CI, domæne for #190–#204), F-AUD26-01 rettet + test, register genereret. Beslutning: NO-GO.
- Ikke færdigt / blokeret: uafhængig verifier (intet Agent-værktøj), Privat-dybdekatalog på kandidaten, belastningstest, backup-restore, udbyder-sandkasser, beslutning på F-AUD26-02.

## Genkørsel
```bash
# 1. worktree fra main + egne databaser/porte (8 GB maskine: én stak ad gangen, tjek free -g)
git -C /home/claude/dialogbot fetch && git -C /home/claude/dialogbot worktree add /home/claude/wt-<run> origin/main
service postgresql start; export PGPASSWORD=postgres
psql -U postgres -h localhost -c "create database qa_<run>" -c "create database qa_<run>_test"

# 2. backend som CI (KUN disse env – e2e-env.sh i pytest giver falske røde)
env -i HOME=$HOME PATH=/home/claude/venv/bin:/usr/bin:/bin APP_ENV=test ENABLE_DEV_TOOLS=true \
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_<run>_test \
  TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_<run>_test \
  bash -c 'ruff check app tests scripts client voice_pipeline tts_service browser_worker && alembic upgrade head && alembic check && pytest -q --junitxml=pytest.xml'

# 3. web + journeys (stak: /home/claude/e2e-env.sh + egne porte, se /home/claude/audit26/env.sh)
cd web && npm ci && npx tsc --noEmit && npm run i18n:check && npm run build
npm run start -- -p <port> &   # API/worker: uvicorn app.main:app --port <api> ; python -m app.worker.runner
PW_SKIP_QA=1 npx playwright test           # = CI-jobbet journeys
npx playwright test e2e/qa --shard=1/4     # katalog (springer privat-deep over uden QA-stak – tæl skipped!)

# 4. register + matrix
python -m scripts.qa_audit_register docs/qa/<run-id>

# 5. CI-skip-tælling (primær evidens)
gh api repos/TigerMonkRep/dialogbot/actions/runs/<run>/jobs --jq '.jobs[]|"\(.id) \(.name) \(.conclusion)"'
gh api repos/TigerMonkRep/dialogbot/actions/jobs/<id>/logs | grep -oE '[0-9]+ (passed|skipped|failed|flaky)'
```

## Til verifier (opgave for hovedsessionen – start med subagent_type: verifier)
1. Kandidat = HEAD af `qa/platform-audit-2026-11-12`. Læs `qa/findings/F-AUD26-01-X29.md` (trin og forventet først).
2. Bevis rød uden rettelsen: `git stash`-revert af `web/next.config.ts`, byg, kør `web/e2e/security-headers.spec.ts` → 7 fejl; med rettelsen → 7 grønne. Tjek at webchat-widgetten (API-origin) stadig kan indlejres.
3. Kør journeys + CI på PR'en. Afgør closed/reopened; opdatér fundfil og ledger.
4. Gennemgå F-AUD26-02/03 og de 10 S1/S0-fund med status `fixed`/`fix-ready`/`new` i findings-register.csv (luk eller genåbn med evidens).
