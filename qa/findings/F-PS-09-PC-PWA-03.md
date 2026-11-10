---
id: F-PS-09-PC-PWA-03
scenario: PC-PWA-03
reported_by: security-privacy
severity: S3
status: new
owner_fix: ui-ux-engineer
related: [F-PS-07-PC-SEC-03]
---

## Kort
Log ud fjerner kun simuleringens login-flag, ikke simuleringens data (sessionStorage `dialogbot-privat-fake`).

## Trin til at genskabe
1. Kom i simulering (F-PS-07 eller `NEXT_PUBLIC_PRIVAT_FAKE=1`), lav en liste med navne/numre.
2. Log ud (shell.tsx `logout`) og log ind som en anden på samme fane.

## Forventet
PC-PWA-03: «Ingen data fra forrige bruger (sessionStorage fake-state, SW-cache, bootstrap)». SW-cache ryddes (`clearSwPages`) – godt.

## Faktisk
shell.tsx logout: `sessionStorage.removeItem("dialogbot-privat-fake-login")` – `dialogbot-privat-fake` (FAKE_KEY med lister/grupper) bliver liggende i fanen. Kun relevant i simuleringstilstand; rigtige data hentes fra API'et med den nye session.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_pwa_03_logout_clears_the_simulation_state (rød)

## Rodårsag (forslag)
Fjern også `FAKE_KEY` og `PENDING_KEY` ved logout (eller `sessionStorage.clear()` for Privat-nøgler).

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Dom: closed | reopened
