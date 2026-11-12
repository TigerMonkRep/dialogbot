# 2. Teststrategi, lanceringsomfang, risici og gates

## Tilsigtet lancering (fra docs + beslutninger, ikke en lettere beta)
Offentlig lancering af **Dialogbot** på dialogbot.app:
- **Erhverv:** døgnåben selvbetjent tilmelding (#193), guiden efter kanaler med betaling som sidste trin (#200), AI-reception (telefon), webchat, booking/kalender, viden inkl. import fra fil og tekst (#196), kampagner (udgående opkald), live-gate kun ved betalt abonnement + 7 dages respit (#200), én plan for Erhverv (Fürsters beslutning). Rebotti er en Erhverv-testkunde.
- **Privat:** liste-, påmindelses- og «Ring for mig»-app med Opkaldssaldo (#190 m.fl.), planer Basis/Plus/Familie, ønskelister, invitationer, «Min dag» (#202).
- **Salg:** «Ring mig op nu» straks døgnet rundt (#198, beslutning). Cold outreach (#204) findes, men er **slået fra** (OUTREACH_MODE=off) – udenfor lancering, men eksponeret kode (operator-API'er) skal være sikker.

| Klasse | Indhold |
|---|---|
| Krævet til lancering | Alt P0/P1 i `qa/scenarios.csv` og `qa/privat/scenarios.csv`, undtagen rækker flyttet ud ved beslutning |
| Valgfrit men eksponeret | Cold-outreach operator-API'er og /unsubscribe; Travelpayouts-verifikation på /privat bag flag (beslutning B, under udvikling) |
| Senere | Egen opkaldsmotor (PR #117 kladde), M03/M06/H01 (not-implemented – se rapport) |
| Uklart → produktfortolkning | «Én plan for Erhverv» vs. kampagne-scenarier C09/C15/B03–B05 (minutpakke-modellen); /demo-call nummer-ejerskab (F-AUD26-02) |

**Fürsters åbne beslutninger – NOT a defect:** Travelpayouts-verifikation (B: script kun på /privat bag flag), PDF uden tekstlag uden OCR (accepteret), én plan for Erhverv.

## Risikoprioritering
1. S0-klasse: rigtige opkald/SMS/e-mails til forkerte personer; penge (Stripe, Opkaldssaldo, respit); tenant-isolation; konto-overtagelse.
2. Dagens 15 merges (#190–#204) – nyeste kode, mindst afprøvet.
3. CI-gatens dækning (hvad der faktisk kører vs. springes over).
4. Produktionsparitet (migration-head, headers, offentlige sider) – kun read-only.

## Acceptance gates (briefens §10 oversat)
| Gate | Bevis der kræves |
|---|---|
| G1 Krævede rejser og forretningsregler | P0+P1 = PASS i traceability.csv |
| G2 Release-checks på kandidaten | pytest, ruff, alembic check, OpenAPI/prices-cmp, tsc, i18n:check, `next build`, journeys-e2e grønne på kandidat-SHA |
| G3 Ingen åbne S0/S1 | findings-register.csv `launch_blocker=yes` = 0 |
| G4 Isolation, integrationer, dataintegritet, recovery | X29/X20-sweep grøn; udbyder-sandkasser verificeret; backup-restore testet |
| G5 Kapacitet | Målt mod erklæret belastning |
| G6 Sign-off | Uafhængig verifier + menneskelig accept (Fürster) + jurist på vilkår/outreach-matrix |

## Miljøer
- Lokal stak: PostgreSQL 16 (`qa_audit26`, `qa_audit26_test`, `qa_audit26_t2`), API :8126, worker, Next (prod-build) :3126, alle udbydere fake (`/home/claude/e2e-env.sh` + `/home/claude/audit26/env.sh`).
- CI: GitHub Actions runs 43240805372 (CI) og 43240805270 (E2E) på 14edd47.
- Produktion: kun GET mod https://dialogbot.app og /health/ready. Ingen login, ingen formularer.

## Provisoriske ydelsesantagelser
Ingen dokumenteret belastningsprofil fundet. Antagelse: < 50 samtidige besøgende, < 20 demo-opkald/time (SALES_MAX_CALLS_PER_HOUR), < 100 aktive arbejdsrum ved lancering. Ingen belastningstest er kørt (se rapport) – G5 er derfor ikke opfyldt.
