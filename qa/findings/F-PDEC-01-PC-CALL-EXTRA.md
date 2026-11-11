---
id: F-PDEC-01-PC-CALL-EXTRA
scenario: PC-CALL / PC-SUB-21 / PC-ENT
reported_by: qa-lead (beslutning Fürster 2026-11-11)
severity: S1
status: fixed
owner_fix: fix-engineer #7
related: [F-PFX-07-PC-CALL-DIALLING, F-PBQ-03-PC-SUB-21, F-PBQ-05-PC-SUB-21, F-PQ-03-X09]
---

## Kort
Beslutning: ekstra opkald i Privat følger Erhvervs prismodel (pris pr. udfald + minut) plus moms, og credits
erstattes af en forudbetalt saldo i kroner («Opkaldssaldo»).

## Krav (fra qa-lead, 11/11)
1. **Priser for ekstra opkald** (ud over planens opkald pr. måned: Basis 3 / Plus 10 / Familie 25), afledt af Erhvervs
   nettopriser i markets/prices (samme kilde som prices.json) × 1,25 – ikke hardkodet:
   besvaret 5 kr. · telefonsvarer 1,25 kr. · ubesvaret/optaget 0,3125 → 0,31 kr. (hele øre, ét sted, testet) ·
   2,50 kr. pr. påbegyndt samtaleminut · højst 14 kr. × 1,25 = 17,50 kr. pr. opkald. Fremmede valutaer: samme
   faktor/regel som markets bruger for Privat.
2. **Hvornår:** kun opkald efter planens kvote. Inden for kvoten: intet ekstra. Ubesvarede opkald tæller stadig ikke mod
   kvoten, men et ubesvaret EKSTRA opkald koster ubesvaret-prisen. «Ring for mig» uden plan: 409 needs_plan.
3. **Saldo i kr.:** ledgeren bliver Opkaldssaldo i øre; ingen antal credits i UI/API/mails. Optankning via Stripe Checkout
   (mode=payment) 50/100/200 kr. inkl. moms, webhooken tjekker det betalte beløb. Velkomstbonus 10 kr. Henvisning 10 kr. til
   hver efter den henvistes første betalte periode (månedsgrænsen bevares). Ekstra opgave 3 kr. (sponsor bevares).
   Migration oven på d7f2b9c4e1a8: 1 credit = 2,90 kr.; testet op/ned/op; alembic check ren.
4. **Reservation:** maks. (17,50 kr.) reserveres før et ekstra opkald, ellers 409 «Fyld op» med CTA. Efter opkaldet
   trækkes den faktiske pris (udfald + påbegyndte minutter fra Vapi), resten frigives. Vapi-fejl frigiver alt
   (jf. F-PFX-07). Idempotent pr. opkald.
5. **Overalt:** Privat-UI (betalingsark, konto/saldo, opkaldskort med pris før godkendelse, historik), prisside/landing,
   katalog, vilkår (8 sprog), llms.txt, mails, fake-API.
6. **Tests:** hver regel har en test, der fejler på 480aafe og består efter.

## Rodårsag (fix-engineer)
Ikke en fejl, men en produktbeslutning: Privat solgte ekstra opkald som credits (10 for 29 kr., 3 pr. besvaret opkald),
mens Erhverv (beslutning 2026-11-10) prissætter opkald pr. udfald. Bemærk: prismodellen pr. udfald ligger på
`qa/decisions-2026-11-10` (631cecc) og var IKKE med på `qa/privat-deep`. Nettopriserne pr. udfald er derfor tilføjet her med
præcis samme navne og værdier (prices.OUTBOUND_CALL_*, markets.ERHVERV[*].call_*), så en senere merge kun giver en
triviel konflikt. Erhvervs egen fakturering er ikke rørt på denne branch.

## Rettelse
- Priser: `app/modules/billing/prices.py` (OUTBOUND_CALL_*, `gross_minor` = den ene afrunding, half-up til hele øre;
  saldo-konstanter), `app/modules/billing/markets.py` (`privat_extra_call`, `privat_extra_call_price`, `privat_from_dkk`,
  `PRIVAT_TOPUPS`, export → prices.json `privatExtraCall`/`privatTopups`/`privatBalance`).
- Migration `alembic/versions/f3a8c6d2b5e9_privat_call_balance_in_ore.py`: amount × 290, kolonne `currency`, kind
  `convert`, paid_via 'credits'→'balance', paid_by 'credit'→'balance'; downgrade ÷ 290 (afrundet; ikke-DKK/convert slettes).
- Backend: `privat/ledger.py` (valuta, reserve/settle én gang, adopt_currency, summary), `privat/calls.py` (reservation
  17,50 kr., 409 insufficient_balance + CTA, afregning pr. udfald/minutter, Vapi-fejl → frigiv alt), `privat/payments.py`
  (optankning 50/100/200, beløbstjek, gamle kreditpakke-sessioner = 29 kr.), `privat/service.py` (ekstra opgave 3 kr.,
  /me-felter), `privat/referrals.py` (10 kr.), `privat/deps.py` (10 kr. velkomst), `privat/router.py`
  (`POST /privat/balance/checkout`, `/privat/credits/checkout` fjernet), `privat/subscriptions.py`, `privat/addons.py`,
  `privat/gdpr.py`, `browser/*` (booking 2,90 kr.).
- Web: `web/src/lib/privat/saldo.ts` (ny), `markets.ts`, `api.ts`, `fake.ts`, `components/privat/{account,cards,day,sheets,shell,tasks}.tsx`,
  `privat.json` × 8, `e2e/privat.spec.ts`.
- Docs: pricing.md, markets.md, privat-api.md, ADR-004, environment-variables.md, implementation-progress.md; openapi.json,
  prices.json og addons-catalog.json regenereret.
- Tests: `tests/test_privat_call_balance.py` (21 tests – alle røde på 480aafe, grønne efter) + tilpassede credits-tests
  (test_privat, test_privat_subscription, test_privat_sharing, test_prices, test_markets, test_browser_*, test_privat_gdpr,
  test_privat_branding, test_privat_places_push, tests/qa/test_qa_pd_billing, test_qa_privat_x09, test_qa_pd_x).
- Commits: 1221306 (backend+migration+tests), 2b82b75 (web), 48fd4de (docs).

## Beslutninger taget af fix-engineer (skal bekræftes – needs-decision hvis uenig)
1. Afrunding: half-up til hele øre pr. prisdel (0,3125 → 0,31; SEK 7,375 → 7,38); prisen for et opkald = udfaldspris +
   minutter × minutpris, højst maks.
2. Maks. 17,50 kr. = Erhvervs ærlige maks. pr. kontakt (2 × besvaret + 3 minutter) × 1,25 – i alle valutaer.
3. Minutter tælles kun for besvarede opkald (som Erhverv: kun en samtale har minutter); varighed fra Vapi `durationSeconds`,
   påbegyndte minutter = ceil(sek./60).
4. «Vapi fejler» = create_call-fejl, `endedReason` der indeholder «error» (og ikke er et ingen-svar-udfald) eller ingen
   rapport inden 30 min. → alt frigives. `twilio-failed-to-connect-call` m.fl. tæller som ubesvaret (0,31 kr.), som hos Erhverv.
5. Fremmede valutaer, opkaldspriser: markedets egne Erhverv-nettopriser × 1,25. Optankninger/bonusser/ekstra opgave har
   ingen Erhverv-pris – de er DKK-beløbet × markedets faktor (Erhvervs minutpris-forhold), optankninger rundet til hele
   kroner/euro: SEK 74/148/295, NOK 79/158/315, EUR 7/14/27; velkomst/henvisning SEK 14,75 / NOK 15,75 / € 1,35.
   **Ikke besluttet af Fürster – bør bekræftes.**
6. Saldoen føres i kontoens valuta (abonnementets, ellers DKK). Velkomstbonussen gives i DKK ved oprettelse og flyttes
   én gang til kontoens valuta ved første Checkout i en anden valuta.
7. Hjemmesidebooking (browser-worker) kostede 1 credit og har ingen egen pris: nu 2,90 kr. (den omregnede credit).
   **Kræver Fürsters beslutning.**
8. Kreditpakke-sessioner åbnet før skiftet og betalt efter lægger det betalte (29 kr. / 45 kr / 45 kr / €3,99) på saldoen.

## Ikke gjort
- **Vilkår for Privat (8 sprog):** findes ikke. Privat-landingens «Handelsbetingelser» peger på Erhvervs `/vilkaar`
  (legal.json), som ikke nævner credits. At skrive nye juridiske vilkår er Fürsters beslutning → needs-decision.
- **llms.txt:** nævner ikke Privat eller credits – intet at rette (Erhverv-linjen står med den gamle kampagnepris fra denne
  branch; A' ligger på qa/decisions-2026-11-10).
- Erhvervs fakturering pr. udfald (statement/campaigns) er ikke flyttet hertil; kun nettopriserne.
- Ingen browser-/e2e-kørsel (ingen stak/build efter ordre); e2e/privat.spec.ts er tilpasset, ikke kørt.
- Refusion af en optankning (F-PBQ-05) trækker stadig ikke beløbet tilbage – uændret kendt fund, testen er tilpasset til øre.

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
