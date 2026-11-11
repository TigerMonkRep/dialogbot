---
id: F-PX-02-PC-APP-04
scenario: PC-APP-04
reported_by: voice-qa (PX)
severity: S2
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Læge & tandlæge-opkald erstatter hele «Du må IKKE»-listen med én helbredslinje – de generelle forbud (betale, give andre oplysninger end navnet, sige ja til ekstra arbejde eller andre tider) forsvinder fra manuset.

## Trin til at genskabe
1. Slå «Læge & tandlæge» til, gem lægen (navn + nummer).
2. «Book en lægetid, helst i morgen formiddag» → `tool_book_health_appointment`.
3. Se `private_calls.may_not` / systemprompten «Du må IKKE: …».

## Forventet
Butikkens løfte (addons.py, ring-for-mig + laege-og-tandlaege): «Siger kun dit navn og det, du selv har skrevet». Standard-`may_not` i `calls.propose` = «Betale, give andre oplysninger end dit navn, eller sige ja til ekstra arbejde eller andre tider». Helbredslinjen skal LÆGGES TIL, ikke erstatte.

## Faktisk
`may_not` = «Fortæl ikke andet om mit helbred end det, der står i formålet.» – intet om betaling, andre tider eller andre oplysninger.

## Evidens
- Test: tests/qa/test_qa_pd_x.py::test_px_app_04_health_purpose_and_may_not (rød)
- Kode: app/modules/privat/chat.py `tool_book_health_appointment` (data["may_not"])
- Kun klinik navn+nummer gemmes i appdata (symptomer gemmes ikke) – det del af PC-APP-04 er OK.

## Forslag
`may_not = DEFAULT_MAY_NOT + " Fortæl ikke andet om mit helbred end det, der står i formålet."` (samme mønster bør tjekkes for bil-og-syn, kæledyr, abonnementer).

## Rodårsag (udfyldes af fix-engineer)
## Rettelse (udfyldes af fix-engineer)
- Rettelse: calls.propose bruger nu _may_not(). De generelle forbud (DEFAULT_MAY_NOT: betale, andre oplysninger end navnet, ja til ekstra arbejde eller andre tider) gælder altid, og en apps egen regel (helbred, opsigelse …) lægges til.
- Filer: app/modules/privat/calls.py
- Test: tests/qa/test_qa_pd_x.py::test_px_app_04_health_purpose_and_may_not (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_px_app_04_health_purpose_and_may_not
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: samme testfil
- Dom: closed
