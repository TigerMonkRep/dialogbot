---
id: F-AUD26-03-CI
scenario: CI
reported_by: qa-lead (platform-audit 2026-11-12, test-infrastruktur)
severity: S2
status: confirmed
owner_fix: fix-engineer (CI) + e2e-privat
related: [beslutning 11/11 qa-catalog continue-on-error]
---

## Kort
Den grønne E2E-kørsel på main (14edd47, run 43240805270) springer ~420 Playwright-tests over uden at fejle: qa-catalog shard 2 og 4 = 150 + 148 skipped (hele e2e/qa/privat-deep + X04/X07, fordi de kræver en Privat-QA-stak på :8100/:8400 som CI ikke starter), journeys = 116 skipped (privat.spec/funnel.spec, som kører i privat-jobbet). qa-catalog er desuden `continue-on-error`.

## Forventet
Briefens §5: skippede tests skal være synlige og begrundede; en grøn job-status må ikke skjule, at Privat-dybdekataloget (P0-scenarier som X04 prøveperiode-funnel og X07) aldrig kører i CI.

## Faktisk
Se qa/evidence/AUD26/ci-skips.txt (tal fra job-logs). Privat-dybdekataloget bevises kun af lokale agentkørsler.

## Forslag
1. Start `tests/qa/qa_privat_stack.py` i et CI-job (eller et natligt workflow) og kør e2e/qa/privat-deep der.
2. Skriv antal skipped pr. job i job-summary og fejl, hvis tallet stiger uden en ændring i en allowlist.
3. Gør qa-catalog blokerende igen, når 1–2 er på plads (Fürsters beslutning 11/11 – needs-decision).

## Status
Ikke rettet i denne kørsel (CI-ændring + ny stak i CI er større end en fokuseret rettelse).
