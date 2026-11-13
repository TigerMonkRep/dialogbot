---
id: F-LEAD1113-01-CI
scenario: CI (Deploy check / schema-head)
reported_by: qa-lead (Erhverv-P0-runde 13/11)
severity: S2
status: fixing
owner_fix: fix-engineer
related: []
---

## Kort
Den planlagte Deploy check (schema-head) er rød på main 8df2c99, fordi `scripts/check_live_schema.py` ikke læser merge-revisioner med tuple som `down_revision` og derfor finder fem «heads».

## Trin til at genskabe
1. main 8df2c99: `python3 -c "import sys; sys.path.insert(0,'scripts'); import check_live_schema as c; c.code_head()"`.
2. Eller se GitHub Actions job 132012362757 (Deploy check, 2026-11-13 16:24).

## Forventet
Ét head, som `alembic heads` (d6f2a8c4e1b7), og derefter sammenligning med produktionens /health/ready (kun GET).

## Faktisk
`expected exactly one Alembic head in the code, found: ['1d2e6f8b0c4a', '2e3f7a9c1d5b', 'a7d3e9c1b5f2', 'd6f2a8c4e1b7', 'e9a1c3b5d7f2']`. Overvågningen af produktionens skema er dermed blind (altid rød), indtil scriptet rettes.

## Evidens
- Job-log 132012362757; seneste grønne kørsel 164311a (før merge-revisionerne e9a1c3b5d7f2/f1b3d5a7c9e2).

## Rodårsag (udfyldes af fix-engineer)
Regex'en for `down_revision` matcher kun én streng; `down_revision = ("a", "b")` blev sprunget over.

## Rettelse (udfyldes af fix-engineer)
- Filer: scripts/check_live_schema.py, tests/test_schema_head.py (`test_deploy_check_script_finds_the_same_single_head_as_alembic`, rød før/grøn efter)
- Commit: branch fix/deploy-check-merge-heads, PR #230

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
