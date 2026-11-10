---
id: F-PB-01-PC-APP-KAELEDYR-04
scenario: PC-APP-KAELEDYR-04
reported_by: e2e-privat (PB)
severity: S1
status: new
owner_fix: fix-engineer
related: [PC-APP-KAELEDYR-03, alle husstandsapps der bruger app_kit.find]
---

## Kort
Et nyt dyr, hvis navn står inde i et andet dyrs navn («Mis» / «Misser», «Bo» / «Bobby»), bliver ikke oprettet. I stedet overskrives det første dyrs data i stilhed, og man kan ikke oprette det andet dyr via chatten.

## Trin til at genskabe
1. Plus/prøve-konto, slå Kæledyr til.
2. Chat: «Vores kat Misser skal vaccineres 2027-03-01» → «Gemt: Misser (kat), vaccination 1. marts 2027.»
3. Chat: «Vores kat Mis skal vaccineres 2027-06-15» → «Gemt: Misser (kat), vaccination 15. juni 2027.»
4. `GET /privat/apps/kaeledyr/overview` → kun «Misser» med vaccination 15. juni 2027.

## Forventet
Scenarie PC-APP-KAELEDYR-04: «Ret overskriver i stedet for dublet», dvs. at kun SAMME navn retter. Et andet dyr (Mis) skal oprettes, og Missers vaccination skal stadig være 1. marts.

## Faktisk
`app_kit.find()` (app/modules/privat/app_kit.py:119-124) finder først et eksakt match og falder ellers tilbage til et delstrengsmatch (`w in key_of(name) or key_of(name) in w`). «mis» ⊂ «misser», så `pets.save_pet` opdaterer Misser. Konsekvens: Missers påmindelse om vaccination kommer 3½ måned for sent, og Mis findes ikke. Det samme `find` bruges af de andre husstandsapps (garanti, abonnementer, hus, fest …), så de rammes formentlig på samme måde.

## Evidens
- qa/evidence/PC-APP-KAELEDYR-04/PB-pet-substring-overwrite.json (live-stak :8400, chat + overview + DB-række)
- Test: tests/qa/test_qa_pd_apps_b.py::test_04_pets_new_name_containing_an_existing_name_is_a_new_pet (fejler i dag)

## Forslag
Ved oprettelse/«gem» kun eksakt match på `key_of(name)`. Delstrengsmatch kan bevares til «fjern …»/opslag, hvor der kun er ét entydigt hit, men ikke til at vælge, hvilken række der skal overskrives.

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
