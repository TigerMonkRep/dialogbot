---
id: F-PX-01-PC-CALL-08
scenario: PC-CALL-08
reported_by: voice-qa (PX)
severity: S2
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
«Nummeret skal være skrevet af brugeren»-vagten (`chat._user_wrote`) matcher 8 cifre som delstreng af ethvert tal i de seneste beskeder – et ordre-/kontonummer kan derfor blive til et telefonnummer i et opkaldsforslag.

## Trin til at genskabe
1. Brugeren skriver «Lav en liste med ordrenummer 4433221100998877».
2. Modellen kalder `propose_call(business_name="Frisør Hansen", phone="22110099")` (cifrene står midt i ordrenummeret).
3. Der oprettes et forslag til +45 22 11 00 99.

## Forventet
coverage.md/PC-CALL-08: «Model opfinder et telefonnummer … Nummer droppes (_user_wrote) → needs_business_phone». Et nummer tæller kun som skrevet, når det står som et selvstændigt telefonnummer (8 cifre, evt. +45/mellemrum), ikke inde i et længere ciffer-løb.

## Faktisk
`_user_wrote` fjerner alle ikke-cifre fra hele beskeden og tester `national in digits` → forslag oprettet («Forslag oprettet … brugeren skal godkende»). Brugeren skal stadig godkende, og nummeret vises på kortet – derfor S2, ikke S0.

## Evidens
- Test: tests/qa/test_qa_pd_x.py::test_px_call_08_invented_number_inside_other_digits (rød)

## Forslag
Match med regex på ord-/ciffergrænser, fx `(?<!\d)(?:\+?45[\s-]?)?(\d{2}[\s-]?\d{2}[\s-]?\d{2}[\s-]?\d{2})(?!\d)` pr. besked, og sammenlign de fundne numre.

## Rodårsag (udfyldes af fix-engineer)
## Rettelse (udfyldes af fix-engineer)
- Rodårsag: chat._user_wrote fjernede alle ikke-cifre fra beskeden og søgte 8 cifre som delstreng.
- Rettelse: chat._phone_numbers finder kun selvstændige telefonnumre (8 cifre, evt. med +45/0045, mellemrum, bindestreg eller punktum) og aldrig cifre inde i et længere ciffer-løb (ordre-/kontonumre). Flere numre adskilt af mellemrum genkendes hver for sig.
- Filer: app/modules/privat/chat.py
- Test: tests/qa/test_qa_pd_x.py::test_px_call_08_invented_number_inside_other_digits (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_px_call_08_invented_number_inside_other_digits
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: samme testfil
- Dom: closed
