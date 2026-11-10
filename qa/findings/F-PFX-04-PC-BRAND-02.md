---
id: F-PFX-04-PC-BRAND-02
scenario: PC-BRAND-02
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S3
status: fixed
owner_fix: fix-engineer
related: []
---

## Kort
Privats browser-theme-color og manifest brugte #E0521A, men brand-accenten er #C4461A.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: web/src/app/privat/layout.tsx themeColor og web/src/app/privat/manifest.webmanifest/route.ts theme_color er sat til #C4461A, og kommentaren i globals.css er rettet. Marketingsider er uændrede.
- Ikke ændret: web/src/components/install-app.tsx:73 bruger stadig #E0521A til Privat-installérkortet (ui-ux).
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
