---
id: F-VF-06-PC-TERMS
scenario: PRIVAT-TERMS / PC-ACC-03
reported_by: verifier
severity: S3
status: fixed
owner_fix: fix-engineer
related: [F-PDEC-03-PRIVAT-TERMS, F-PDEC-02-PC-WEBBOOK]
---

## Kort
1. «Slet min konto» (15c3704, 8 sprog) siger «En resterende Opkaldssaldo går tabt og refunderes ikke», men vilkårenes punkt 7/8 giver fortrydelsesret på den ubrugte del af en optankning i 14 dage. Sletter man inden for 14 dage efter en optankning, er advarslen i appen strengere end vilkårene. Forslag: «… refunderes ikke (bortset fra fortrydelsesretten, se vilkårene)».
2. Vilkårene beskriver hjemmesidebooking som «fair use», men koden har et hårdt loft på 30 pr. kalendermåned (429 browser_booking_limit). Skal tallet stå i vilkårene?
3. Optanknings-arket siger «Saldoen udløber ikke i piloten», mens vilkårene siger, at den ikke udløber, så længe kontoen findes.

## Beslutning (Fürster 2026-11-11)
1. «Slet min konto» får undtagelsen om fortrydelsesret (ubrugt del af en optankning inden for 14 dage).
2. Vilkårene beholder «fair use» uden tal; koden beholder loftet på 30. Ingen brugertekst må nævne 30.
3. Optanknings-arket skal sige det samme som vilkårene: saldoen udløber ikke, så længe kontoen findes.

## Rodårsag (fix-engineer #13)
Teksterne i privat.json (myData.deleteText, buy.note) blev skrevet før vilkårenes punkt 8 (Opkaldssaldo) blev besluttet 11/11 og blev ikke opdateret sammen med privatTerms. Der var ingen test, der holdt app-teksterne op mod vilkårene.

## Rettelse (fix-engineer #13)
- myData.deleteText ×8: «… går tabt og refunderes ikke – undtagen inden for 14 dage efter en optankning, hvor du kan fortryde den ubrugte del af optankningen (se vilkårene, punkt 7). Sletningen kan ikke fortrydes.» («Det» → «Sletningen», så sætningen ikke kan læses som om fortrydelsen ikke kan fortrydes.)
- buy.note ×8: «Engangsbetaling, intet abonnement. Saldoen udløber ikke, så længe kontoen findes.» (samme ordlyd som privatTerms pr. sprog).
- Punkt 2: ingen kodeændring. Gennemgået: ingen tekst i privat.json `browser.*` eller i privatTerms' booking-afsnit nævner et tal; loftet ligger kun i prices.PRIVAT_BROWSER_BOOKINGS_PER_MONTH = 30 (skjult, 429 browser_booking_limit).
- Filer: web/src/i18n/messages/{da,de,en,es,fr,it,no,sv}/privat.json, tests/test_privat_terms_texts.py (ny)
- Test: tests/test_privat_terms_texts.py – deleteText og buy.note holdes op mod privatTerms' saldo-afsnit pr. sprog (fejler på origin/main 2c24545, består efter); booking-testen er en vagt (består før og efter, da punkt 2 ikke kræver ændring).
- Commit: se branch fix/privat-terms-sponsor (`fix(privat): F-VF-06-PC-TERMS …`)

