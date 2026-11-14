---
id: F-PBQ-06-PC-ENT-02
scenario: PC-ENT-02
reported_by: billing-qa
severity: S1
status: closed
owner_fix: fix-engineer
related: [PC-ENT-03, PC-SUB-15, F-P2-06-X12]
---

## Kort
Plan-apps (16 apps med `included_in` plus/familie) virker for altid efter én prøveperiode. `addons.require()` tjekker kun «slået til», ikke planen (addons.py:9-10 «Once on, it stays on», 808-812). Påmindelser fra Fødselsdage og Regninger sendes også videre til en konto uden plan.

## Trin til at genskabe
1. Ny konto → checkout med kort → trial (Plus).
2. Slå alle plan-apps til (`POST /privat/addons/<key>/enable` for kalender, foedselsdage, madplan, bil-og-syn, regninger, laege-og-tandlaege, pakkeliste, abonnementer, haandvaerker, garanti, flytning, kaeledyr, hus-og-vedligehold, fitness-og-sundhed …).
3. Opsig straks (`customer.subscription.deleted`) og gå 15-20 dage frem → `entitled=false`, `plan=none`.
4. Brug apps via API.

## Forventet
Prisreglen og FEATURES siger, at «Alle apps i Butikken» er med i Plus/Familie. Det er uafklaret, hvad der skal ske, når planen slutter. Beslutningen er Fürsters.

## Faktisk (status quo, verificeret)
- `GET /privat/addons`: alle plan-apps står stadig `enabled`.
- `addons.require(db, ws, key)` kaster ikke for nogen plan-app.
- `GET /privat/bills`, `/privat/birthdays`, `/privat/car`, `/privat/health-contacts`, `/privat/apps/garanti/overview` og `/privat/apps/flytning/overview` svarer 200, og `POST /privat/bills` opretter en ny regning.
- Worker: `birthdays.send_due` og `bills.send_due` sender påmindelser (push eller e-mail) til en konto med `entitled=false`, fordi de kun joiner på `PrivateAddonEnabled`.
- Basis-kunder, der har haft trial eller Plus, beholder Plus-apps efter nedgradering (PC-SUB-15).

## Konsekvens
- Teenager-persona: én 14-dages trial (kort kræves, intet trækkes ved opsigelse i trial) giver alle Plus-apps gratis for evigt. Kun opkald (kvote → credits) og nye opgaver (kladder) stopper.
- Basis (49 kr.) med tidligere Plus = Plus-funktioner for Basis-pris. Det udhuler forskellen på 50 kr./md.
- Påmindelser fortsætter og koster e-mails/push uden betaling.

## Beslutning nødvendig (Fürster)
A. Plan-apps pauses ved planens udløb, så data bevares, men endpoints og påmindelser svarer 409 `needs_plan`, indtil der er en plan igen.
B. «Once on, it stays on» er bevidst (lokkemad), og dokumentationen og prisargumentet tilpasses.
C. Mellemvej: læse-adgang til egne data, men ingen påmindelser og ingen nye poster.

## Evidens
- tests/qa/test_qa_pd_billing.py::test_pc_ent_02_status_quo_what_still_works_after_the_trial (grøn = status quo)
- ::test_pc_ent_02_plan_apps_stop_when_the_plan_ends (xfail strict, `/privat/bills` → 200)
- ::test_pc_ent_03_reminders_from_plan_apps_continue_after_expiry (grøn = påmindelser sendes)
- ::test_pc_sub_15_plan_and_interval_changes_follow_the_price (Familie → Basis: apps forbliver)

## Beslutning (Fürster 12/11, bindende)
Plan-apps fra Butikken – også «Ring for mig» – **stopper**, når prøveperioden udløber uden en betalt plan (mulighed A). Gaten sidder i backend; UI'et viser ærligt «Kræver plan» med en vej til planvalg. Data bevares.

## Rodårsag (udfyldes af fix-engineer)
Backend-delen var allerede bygget efter beslutningen 2026-11-10/11 (commit de11863/099f97e): `addons.enabled_keys` udelader plan-apps uden plan, `addons.require` svarer 403 `needs_plan`, `tools_for` giver ingen chat-værktøjer, og alle påmindelses-jobs går gennem `addons.running_rows` (fødselsdage, regninger, bil, pakker, app_kit). Fundfilen var ikke opdateret. **Det, der manglede, var UI'et:** `addons.out` sender `needs_plan: true`, men web læste det ikke – appen stod som «Slået til» på Mine apps og Min dag, og app-siden viste panelet, som fik `needs_plan` fra sine endpoints (fejlboks i stedet for en ærlig besked).

## Rettelse (udfyldes af fix-engineer)
- Filer: `web/src/lib/privat/api.ts` (`needs_plan` på Addon), `web/src/components/privat/apps.tsx` (badge «Kræver plan»; egen sektion «Sat på pause · kræver en plan» på Mine apps; app-siden viser «{app} er sat på pause … Dine data er gemt» + «Vælg plan»/«Prøv gratis» → PlanSheet, intet panel; ikke på Min dag), `web/src/lib/privat/fake.ts` (fake sætter `needs_plan` som backend), `web/src/i18n/messages/*/privat.json` (8 sprog), `tests/test_privat_plan_apps_lapse.py` (hele kataloget), `web/e2e/privat.spec.ts` (fake-journey).
- Commit: 8ed36d9 (UI), 37fe2de (pytest), se også spec-commit
- Testresultat: `tests/test_privat_plan_apps_lapse.py` 2/2; `tests/qa/test_qa_pd_billing.py::test_pc_ent_02_*`, `::test_pc_ent_03_*` grønne; Privat-fake: se nedenfor.
- Rigtig stak: ikke relevant ud over pytest – gaten er backend-only og testet via API (403 `needs_plan` på app-endpoints, ingen tools, ingen påmindelser); UI'et læser kun `needs_plan`-feltet, som fake-backenden spejler.

## Verifikation (udfyldes af verifier)

## Verifikation (verifier 2026-11-13 b, uafhængig)
- Kandidat: main 39a886f (39a886fe84d12ad261fd1afb27a9aa52e2df431e, ren worktree /home/claude/wt-ver1113b; alembic heads = d6f2a8c4e1b7, ét head)
- Separat spawnet verifier-agent. Rettelserne er ikke skrevet af mig. CI-lignende miljø (APP_ENV=test, ENABLE_DEV_TOOLS, egen DB qa_v1113b_test/qa_v1113b_rev), e2e-stak på egne porte 3437/8437 (DB qa_v1113b_e2e). Fuld pytest og CI på kandidaten: se ledger 2026-11-13 b.
- Gentest: Privat-fake prod-build (NEXT_PUBLIC_PRIVAT_FAKE=1, :3438): `privat.spec.ts:554` (F-PBQ-06) 4/4 (375 + 1440 × begge projekter). Hele privat.spec 116/116. `tests/test_privat_plan_apps_lapse.py` og `test_qa_pd_billing::test_pc_ent_0[23]_*` er grønne.
- Fejler testen uden rettelsen? ja. Når apps.tsx fra 8ed36d9 vendes (fake/api.ts beholdt), fejler 1440-varianterne på «Kræver plan» (element(s) not found). 375-varianterne fejlede i `next dev`, fordi Next.js' dev-overlay opfangede klik. I prod-buildet er de grønne med rettelsen. Det var en harness-fejl og ingen produktfejl.
- Naboscenarier kørt: privat.spec.ts (116, begge viewports)
- Dom: **closed**
- Bemærk: Fixerens ledger nævner kun 1440. Her er 375 også kørt.
