# Verifier: Fürsters beslutninger 2026-11-10 (model A') – uafhængig beregning

Branch `qa/decisions-2026-11-10` @ 631cecc, basis 46a3c54. Kørt 2026-11-11 af verifier.

Kilde for reglerne: kun commit-beskederne c36eca3, 23b79c8 og 631cecc samt docs/pricing.md, ikke koden. Fælles pakke på 300 påbegyndte min/md. (ind og ud), brugt i den rækkefølge opkaldene sker. Inden for pakken er der ingen opkaldspris. Over pakken koster et minut 1,50 kr. ind og 2 kr. ud. Et udgående opkald, der STARTER efter brugt pakke, koster desuden 4 / 1 / 0,25 kr. (besvaret / telefonsvarer / ubesvaret, ukendt = 0,25). Et opkald, der krydser grænsen, deler kun minutterne.

Forventede tal er regnet i hånden. De står også som en lille, selvstændig model (`expected()`) i `tests/qa/test_qa_verify_decisions.py`. Faktisk = `GET /billing/statement` (statement), `GET /billing/usage` (Konto-API), `campaigns.service.max_cost` og operatørens afgørelse.

| # | Scenarie | Forventet (øre, ekskl. moms) | Faktisk | OK |
|---|---|---|---|---|
| V1 | Under 300: ind 100 min + 61 s; ud 125 s besvaret, 0 s ubesvaret, 0 s telefonsvarer | Forbrug 0; pakke brugt 105, tilbage 195; net 249.500, brutto 311.875; ingen `campaign_call_fees` | Samme | ja |
| V2 | Over 300, ind/ud blandet: ind 250 min → ud 125 s besvaret (3) → ind 46 min 1 s (47, fylder pakken præcis) → ud ubesvaret → ud telefonsvarer → ud 61 s besvaret → ind 10 min → ud uden rapport | Gebyrer 25+100+400+25 = 550; ud-min 2×200 = 400; ind-min 10×150 = 1.500; forbrug 2.450; net 251.950, moms 62.988 (½ op), brutto 314.938; pakke 312 brugt / 12 over | Statement: samme linjer (fees 1 besvaret, 1 telefonsvarer, 2 ubesvaret = 550; kampagne 5 opkald, 5 min, 3 pakke, 2 over = 400; ind 307 min, 297 pakke, 10 over = 1.500); Konto-API pr. opkald summerer til 2.450 | ja |
| V3 | Krydser grænsen: ind 295 min → ud 7 min 30 s besvaret (8 min) → ud ubesvaret → ind 2 min; + demoopkald 10 min samme dag | Ud: 5 i pakke, 3×200 = 600, INGEN opkaldspris; næste ud 25; ind 2×150 = 300; demo tæller ikke; forbrug 925 | 925; fees-linje 25 | ja |
| V4 | Efterregistrering: pakke fuld; ud 30/11 23:58 lokal uden rapport og ind 23:59 uden varighed; nov faktureres (25 = ukendt udfald). Rapporter 1/12: besvaret 150 s, ind 4 min | Nov omregnet: 400 + 3×200 + 4×150 = 1.600, faktureret 25 → dec-linje `late_usage_adjustment` 1.575 (7 min, period 2026-11), én gang; jan intet | Samme | ja |
| V5 | Klage godkendt i åben måned: ind 298 min → X ud 3 min besvaret (2 pakke + 1 over = 200) → Y ud 1 min besvaret efter pakken (400+200) | Før 800. Efter godkendelse af X (pool): Y får de 2 ledige min, ingen opkaldspris → 0; pakke 299/1 | `credit_mode=pool`, forbrug 0, pakke 299/1 | ja |
| V6 | Samme, men nov faktureret før godkendelse | Kredit = værdi med X − uden X = 800 − 0 = 800 → dec-linje `dispute_credit` −800, én gang; ingen efterregistrering; jan intet | `credit_mode=invoice`, `credit_net_minor=800`; dec −800; jan intet | ja |
| V7 | V2-data i SEK / NOK / EUR (aftale via API, land SE/NO/DE) | SEK: 2.790 + 810 = 3.600 (net 373.100); NOK: 2.980 + 870 = 3.850 (net 403.350); EUR: 254 + 75 = 329 (net 33.229) | Samme; aftalens `outbound_call` = 590/150/35, 630/160/40, 55/14/3 | ja |
| V8 | max_cost: 10 kontakter med 0 forsøg + 1 med 1 forsøg; 290 min allerede brugt | Forsøg 21, minutter 33; værste fald 21×400 + 33×200 = 15.000; pr. kontakt 1.400; med pakken (10 tilbage): 23×200 + 21×400 = 13.000 | Samme | ja |
| V9 | Udfaldsklasse (Vapi endedReason) | voicemail → telefonsvarer; did-not-answer/busy/failed-to-connect/tavs → ubesvaret; samtale → besvaret | Samme | ja |
| V10 | `statement()` direkte = API | Ens totals | Ens | ja |
| V11 | Loftet 14 kr. pr. kontakt: pakken brugt; telefonsvarer (0 s) → besvaret 180 s | 100 + 400 + 3×200 = 1.100 ≤ `per_contact_net_minor` 1.400; MAX_ATTEMPTS 2 / 180 s | Samme | ja |

Kørsel: `tests/qa/test_qa_verify_decisions.py` gav 10/10 pass på 631cecc. På 46a3c54 fejlede alle 10.

Genkørt 2026-11-11 af ny verifier (forgængeren døde ved genstart): 11/11 pass på 631cecc (db qa_verdec_v11). Med app/ og alembic/ fra 46a3c54 (worktree /home/claude/wt-vd-rollback, db qa_verdec_before) fejler 11/11, inklusive V11.

## Bemærkninger (ikke beregningsfejl)
- `max_cost` regner 14 kr. pr. kontakt (2 × 4 kr. + 3 × 2 kr.), som docs og Fürsters tekst siger. Koden afslutter dog kontakten efter et besvaret opkald (`max_minutes`, `on_report`), så to besvarede forsøg kan ikke ske. Det reelle maksimum er 1 + 4 + 6 = 11 kr. Tallet er altså en øvre grænse og ikke for lavt. Det er en beslutning, ikke en fejl.
- Opkald med samme tidsstempel sorteres efter UUID, så rækkefølgen er vilkårlig. Reglerne siger ikke, hvordan lighed skal håndteres.
- EUR besvaret = 0,55 €, men faktorreglen i `markets.py` giver 0,54 €. Se F-VR-07-X28.
