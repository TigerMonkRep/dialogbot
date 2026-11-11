---
id: F-PFX-05-PC-ENT-02
scenario: PC-ENT-02/03
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S1
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Fürsters beslutning 2026-11-10: apps, der kræver plan, skal stoppe, når planen ikke længere gælder. Data bevares, og appen virker igen, når planen er tilbage.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: addons.enabled_keys() returnerer kun apps, der KØRER. En app med included_in tæller ikke med, når entitlements ikke dækker planen (udløbet trial, opsagt efter periodens slut, unpaid). Da tools, require(), chat og planlagte opkald alle læser enabled_keys/is_enabled, stopper de automatisk. require() svarer 403 `needs_plan` («… dine data er gemt og kommer tilbage, når planen er aktiv igen»). Butik-kortet har nyt felt `needs_plan: true` (UI: «Kræver plan»). Worker-påmindelser stopper via `addons.running_rows`: app_kit.send_due, bills, birthdays, car og parcels. Rækken i private_addon_enabled og appens data bliver liggende, så alt virker igen, når planen er aktiv.
- Fortolkning (bør bekræftes af Fürster): «Ring for mig» (pricing=credits) stopper IKKE uden plan, fordi hvert opkald så betales med 3 credits. Det er produktets credits-vej, og eksisterende tests bygger på den. Gratis apps påvirkes ikke.
- Tests tilpasset: test_privat_calendar (credits-vejen afslutter prøveperioden, og Kalender kræver nu plan → set_plan før rapporten), test_privat_sharing::test_addon_catalog_extensible (nyt felt needs_plan).
- Filer: app/modules/privat/addons.py, app_kit.py, bills.py, birthdays.py, car.py, parcels.py
- Test: tests/test_privat_apps_state.py::test_plan_app_stops_when_the_plan_lapses_and_comes_back_with_its_data
- UI: ui-ux-engineer skal vise `needs_plan` som «Kræver plan» med vej til Konto/checkout.
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_plan_app_stops_when_the_plan_lapses_and_comes_back_with_its_data
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: test_privat_apps_state.py
- Dom: closed
