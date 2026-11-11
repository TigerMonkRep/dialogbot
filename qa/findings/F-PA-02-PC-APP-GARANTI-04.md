---
id: F-PA-02-PC-APP-GARANTI-04
scenario: PC-APP-GARANTI-04
reported_by: e2e-privat (PA)
severity: S2
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Garanti retter aldrig. Den samme besked to gange (genforsøg, dobbelt-tryk, «jeg sagde det i går») giver to ens køb og to påmindelser.

## Trin til at genskabe
1. Slå Garanti til.
2. Chat to gange: «Jeg købte en vaskemaskine i Elgiganten den 2026-05-03 til 4.999 kr.»
3. `GET /privat/apps/garanti/overview` → 2 rækker «Vaskemaskine fra Elgiganten, købt 3. maj 2026 …».

## Forventet
PC-APP-GARANTI-04: «Ret overskriver i stedet for dublet». De andre husstandsapps (abonnementer, fest, fødselsdage) finder rækken med samme navn og retter den.

## Faktisk
`warranty.add()` sætter altid en ny række foran (`rows = [row] + …`). Der er ingen opslag på produkt+butik+dato. Hver dublet giver sin egen 30-dages påmindelse (tag pr. id).

## Evidens
- Test: tests/qa/test_qa_pd_apps_a.py::test_pa_04_garanti_same_purchase_twice_is_two_rows (fejler i dag)

## Forslag
Ret, når produkt+butik+købsdato er ens (eller produkt+butik inden for få dage). To ens maskiner må gerne kræve, at brugeren siger det.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: warranty.add retter et eksisterende køb med samme ting, butik og købsdato i stedet for at lave en ny række (samme id, så der heller ikke kommer en ekstra påmindelse).
- Filer: app/modules/privat/warranty.py
- Test: tests/qa/test_qa_pd_apps_a.py::test_pa_04_garanti_same_purchase_twice_is_two_rows (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_pa_04_garanti_same_purchase_twice_is_two_rows
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: samme testfil
- Dom: closed
