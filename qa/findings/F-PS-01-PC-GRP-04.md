---
id: F-PS-01-PC-GRP-04
scenario: PC-GRP-04
reported_by: security-privacy
severity: S0
status: new
owner_fix: fix-engineer
related: [F-PS-02-PC-INV-05, PC-CALL-12]
---

## Kort
SMS-pumping: det offentlige gruppelink sender verifikations-SMS til vilkårlige udenlandske numre uden samlet loft – én gratis konto kan få Dialogbot til at sende ubegrænset mange SMS (betalt af Dialogbot).

## Trin til at genskabe
1. Gratis Privat-konto (ingen prøveperiode): `POST /privat/groups {"name":"Pump"}`.
2. `POST /privat/groups/{id}/join-link` ×5 (intet loft over antal links pr. gruppe/konto).
3. Uden login, pr. link 20×: `POST /privat/group-invites/by-code/{code}/join {"name":"X","phone":"+88213000001"}` med skiftende `X-Forwarded-For` (se F-PS-02).
4. Tæl SMS i den falske SMS-verden.

## Forventet
groups.py: «CODES_PER_LINK_HOUR = 20 (anti SMS-pumping)». Pumping skal være begrænset pr. konto/ejer og globalt, og koder skal kun sendes til numre, Privat understøtter (UI-tekst: «Skriv dit mobilnummer med 8 cifre» = danske numre).

## Faktisk
100 SMS på få sekunder til +882-numre (international premium-range) fra én gratis konto; antallet skalerer lineært med antal links. `/privat/phone/start` sender også kode til `+447911123456` (200 `{"sent":true}`), loftet er kun 30 s mellem koder pr. konto.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_grp_04_sms_pumping_through_group_join_links_is_unbounded («100 verification SMS to non-Danish numbers»)
- Test: tests/qa/test_qa_pd_sec.py::test_ps_grp_04b_phone_verification_accepts_foreign_numbers
- Kun simuleret SMS (fake connectors); ingen rigtig SMS sendt.

## Rodårsag (forslag)
app/modules/privat/groups.py:366 `normalize()` → campaigns.normalize_phone accepterer enhver E.164 (`^\+[1-9]\d{7,14}$`); grænserne (groups.py:371-378) er pr. link og pr. nummer, ikke pr. ejer/konto/IP/globalt; `create_link` (groups.py) har intet loft. phone.py:40 samme normalisering.
Forslag: (1) kun +45-mobilnumre (eller en eksplicit landeliste) i group-join og phone/start; (2) loft pr. gruppeejer (fx 20 koder/time på tværs af alle links) og et globalt loft på privat-SMS pr. time med alarm; (3) højst ét aktivt link pr. gruppe (create_link genbruger/tilbagekalder det gamle); (4) per-IP-grænsen skal bruge en ikke-forfalskbar IP (F-PS-02).

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
