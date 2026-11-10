---
id: F-PA-02-PC-APP-GARANTI-04
scenario: PC-APP-GARANTI-04
reported_by: e2e-privat (PA)
severity: S2
status: confirmed
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
