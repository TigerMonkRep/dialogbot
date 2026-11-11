---
id: F-PFX-04-PC-BRAND-02
scenario: PC-BRAND-02
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S3
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Privats browser-theme-color og manifest brugte #E0521A, men brand-accenten er #C4461A.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: web/src/app/privat/layout.tsx themeColor og web/src/app/privat/manifest.webmanifest/route.ts theme_color er sat til #C4461A, og kommentaren i globals.css er rettet. Marketingsider er uændrede.
- Ikke ændret: web/src/components/install-app.tsx:73 bruger stadig #E0521A til Privat-installérkortet (ui-ux).
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: /privat har <meta name=theme-color content=#C4461A>; test_jp12 grøn
- Fejler testen uden rettelsen? ja – test_jp12 på 2715783: '#E0521A' != '#C4461A'
- Naboscenarier kørt: -
- Dom: closed
