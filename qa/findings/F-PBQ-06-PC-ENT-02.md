---
id: F-PBQ-06-PC-ENT-02
scenario: PC-ENT-02
reported_by: billing-qa
severity: S1
status: needs-decision
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

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)

## Verifikation (udfyldes af verifier)
