# Billing – forventet vs. faktisk (billing-qa, kørsel 2026-11-10, bølge 1)

Forventede beløb er regnet uafhængigt ud fra prisreglerne (`.claude/agents/billing-qa.md`), ikke ved at kalde koden.
Alle beløb i øre. Erhverv ekskl. moms, Privat inkl. moms. Moms 25 %, half-up på totalen.
Stripe: kun lokale fakes (ingen netværkskald). DB: `qa_bill`. Log: `qa/evidence/<id>/pytest-run-2026-11-10.log`.

## X28 – forbrug (Erhverv, DKK)

| Tilfælde | Forventet | Faktisk (system) | OK | Test |
|---|---|---|---|---|
| Kampagneopkald 0 s besvaret | 400 (0 min) | 400 | ja | x28::campaign_call_minute_boundaries |
| Kampagneopkald 1 s | 400 + 1×200 = 600 | 600 | ja | samme |
| Kampagneopkald 59 s | 600 | 600 | ja | samme |
| Kampagneopkald 60 s | 600 | 600 | ja | samme |
| Kampagneopkald 61 s | 400 + 2×200 = 800 | 800 | ja | samme |
| Ubesvaret kampagneopkald (30 s ringetid) | 400 | 400 | ja | samme |
| Måned: 6 opkald, 5 min + abonnement | netto 252.900 · moms 63.225 · brutto 316.125 | 252.900 / 63.225 / 316.125 | ja | samme |
| Dobbelt end-of-call-rapport (125 s, så 400 s) | prissat én gang: 400 + 3×200 = 1.000 | 1.000 | ja | x28::duplicate_end_of_call_report |
| 60,4 s (brøkdel) | streng læsning 800 (2 påbegyndte min) | 600 (int() kapper) | **needs-decision** F-BQ-001 | x28::fractional_second (xfail) |
| Listepris ændres efter opkaldet | snapshot 400 + 2×200 = 800 | 800 | ja | x28::price_snapshot |
| Indgående 0/1/59/60/61 s + 295 min | 300 min, 0 ekstra, 0 kr. | 300 / 0 / 0 | ja | x28::inbound_boundaries |
| Indgående 301. minut | 1 ekstra = 150; total 249.650 / 62.413 (62.412,5 half-up) / 312.063 | 150; 249.650 / 62.413 / 312.063 | ja | samme |
| Oktober 310 min (sidste kald 31/10 23:59:59 CET) | 10 ekstra = 1.500 | 1.500 | ja | x28::included_minutes_reset |
| November (kald 1/11 00:00 CET = 23:00Z) | 5 min, 0 kr. (300 nulstillet) | 5 / 0 | ja | samme |
| Sommertid start: 31/3 23:59:59 CEST / 1/4 00:00 CEST | marts / april | marts / april | ja | x28::dst_start_month_boundary |
| Sommertid slut: 25/10 02:30 CEST og 02:30 CET | begge oktober | oktober | ja | samme |
| Nytår 31/12 22:59:59Z / 23:00Z | december / januar | december / januar | ja | samme |
| Kampagneopkald dialled 31/3 21:59:59Z / 22:00Z | marts / april | marts / april | ja | x28::campaign_calls_counted_in_copenhagen_month |
| Kampagneopkald også i `calls` | tæller ikke som indgående | ingen indgående linje | ja | x28::campaign_calls_never_count_as_inbound |
| Svensk virksomhed: priser vist på Konto (GET /agreement → plan) | 369.500 / 590 / 295 / 220 SEK | 249.500 / 400 / 200 / 150 (DKK-tal vist som SEK) | **nej** F-BQ-009 | x28::agreement_plan_prices_are_in_the_workspace_currency |
| Konto-tekst kampagneminut | "pr. påbegyndt minut" | "pr. minut" | **nej** F-BQ-010 | x28::konto_text_says_started_minute |

## X08 – Privat (DKK, inkl. moms)

| Tilfælde | Forventet | Faktisk | OK | Test |
|---|---|---|---|---|
| Basis md / år-pr-md / år | 4.900 / 3.900 / 46.800 (=12×3.900) | API = prices.json = samme | ja | x08::plan_amounts_api_ui |
| Plus | 9.900 / 7.900 / 94.800 | samme | ja | samme |
| Familie | 16.900 / 13.500 / 162.000 | samme | ja | samme |
| Årsrabat | ca. 20 % (20,4 / 20,2 / 20,1 %) | inden for 19–21 % | ja | samme |
| Checkout 3 planer × md/år | unit_amount = md-pris / årstotal, inclusive, DK 25 % inkl.-sats, 14 dages trial, kort påkrævet | som forventet (6/6) | ja | x08::checkout_charges_the_listed_amount |
| STRIPE_TAX_ENABLED=true | automatic_tax, tax_code txcd_10103000, inclusive, ingen egne satser | som forventet | ja | x08::stripe_tax_enabled |
| Opsig i prøveperiode (ved periodens udløb) | rettigheder til trial-slut, intet træk, ingen ny trial | som forventet | ja | x08::trial_then_active_and_cancel_inside_the_trial |
| Prøveperiode udløber → aktiv Familie | active, 25 opkald, 5 personer | som forventet | ja | x08::trial_expiry_converts |
| Opsig prøveperiode straks | uafklaret | rettigheder til trial-slut | **needs-decision** F-BQ-005 | x08::immediate_cancel_in_trial (xfail) |
| Fejlet fornyelse (past_due) | rettigheder under rykkerforløb | entitled, 10 opkald | ja | x08::failed_renewal_past_due |
| Opsagt pga. manglende betaling | ingen rettigheder for ubetalt periode | entitled=true, Plus, 10 opkald | **nej** F-BQ-003 | x08::subscription_ended_for_non_payment |
| Basis → Familie i Billing Portal | Familie, 25 opkald, 5 personer | Basis, 3, 1 | **nej** F-BQ-002 | x08::plan_change_in_portal |
| Måned → år i Billing Portal | interval year | month | **nej** F-BQ-002 | x08::month_to_year_in_portal |
| Samme event-id to gange | anden gang uden effekt | "duplicate" | ja | x08::duplicate_event |
| Ældre 'trialing' efter 'active' | forbliver active | expired, ingen rettigheder | **nej** F-BQ-004 | x08::out_of_order_stale_trialing_event |
| Paywall-note efter prøveperiode | 9.900/md (checkout er Plus månedlig) | viser 7.900/md ({pPlusYear}) | **nej** F-BQ-006 | x08::paywall_trial_note |
| Stripe-testkatalogets faste DKK-pris-id'er = prices.py | skal stemme | ikke testbart uden Stripe-netværk | blocked | – |

## B03–B06, DB-001/002/003/012

| Tilfælde | Forventet | Faktisk | OK | Test |
|---|---|---|---|---|
| DB-001: 14 leads + 500 pakker | A = 599.500 (uanset leads), B = 658.600 | 599.500 / 658.600 | ja | db001_db003::model_a_ignores_leads |
| DB-002: tvist uden faktura, uphold | 208.600 godkendt / 14.900 suspenderet / ingen kreditnota | samme | ja (ren regel) | b03::db002, b04 |
| DB-002: reject | 223.500 / 14.900 / ingen kreditnota | samme | ja (ren regel) | samme |
| DB-002: allerede faktureret gren | separat sti | findes ikke | not-implemented | b04::already_invoiced_branch |
| Legacy model B: 14 × 149 kr. | 208.600 / 52.150 / 260.750 | samme | ja | b03::legacy_model_b |
| Godkendt henvendelse under abonnement | fee 0, besluttes én gang, idempotent replay | som forventet | ja | b03::approval_under_the_subscription |
| DB-003: 301 kontakter, 420 forsøg | counts.total 301, counts.calls 420, faktureret 420 × 400 = 168.000 | samme | ja | db001_db003::contacts_and_attempts |
| DB-012: 500 pakker | 450.000 / 112.500 / 562.500 | samme | ja (ren regel) | b05::db012 |
| DB-012: 200 ubrugte | 180.000 / 45.000 / 225.000 | samme | ja (ren regel) | samme |
| Half-up på øre: 150 / 1 / 2 | moms 38 / 0 / 1 | samme | ja | samme |
| Aftalepris efter listeprisændring | gammel måned 249.500 | 249.500 | ja | b05::agreement_price_snapshot |
| Faktura open→paid / payment_failed / uncollectible | paid / payment_failed / failed, PDF+nummer gemt | samme | ja | b06::states |
| Stripe-total afviger 1 øre | markeres i note, overskrives ikke | note "afviger" | ja | samme |
| Stripe Tax-beløb | net/tax/gross fra Stripe (249.500 / 62.376 / 311.876) | samme | ja | b06::stripe_tax_amounts |
| payment_failed ankommer efter paid | forbliver paid | payment_failed | **nej** F-BQ-007 | b06::late_payment_failed |
| Provision 24.950; refusion 20 % + 20 % (kumulativ 40 %) | 14.970 | 11.976 | **nej** F-BQ-008 | b06::two_partial_refunds |
| Én refusion som kreditnota + charge.refunded | 19.960 | 15.968 | **nej** F-BQ-008 | b06::one_refund_reported_as_refund_and_credit_note |
| Ordre-detalje, tvistcenter, fakturadetalje-rute, 'adjusted' | – | ikke bygget | not-implemented | b03/b04/b05/b06 ::…not_built |

## Kendte risici uden fund (kan ikke bevises offline)

- Stripe beregner moms med `default_tax_rates` pr. linje; vores oversigt runder half-up på totalen. Med to linjer med ,5 øre moms (fx 1 ekstra indgående minut à 150 + en rabatlinje) kan de afvige 1 øre. Koden fanger det (`invoices.note`), men det gemte `gross_minor` er vores, ikke det trukne. Kræver Stripe test mode at bevise.
- Konto-siden beregner "forrige måned" for "Fakturér nu" i UTC (`new Date().toISOString()`), ikke Europe/Copenhagen: 1. i måneden 00:00–01:00/02:00 lokal tid foreslås den forkerte måned (backend afviser ikke-afsluttede måneder, så intet faktureres forkert).
- Faste DKK Stripe-pris-id'er (`PRIVAT_STRIPE_PRICE_*`) har intet tjek mod `prices.py`; et forkert katalogbeløb vil blive trukket uden at nogen test opdager det.

## Minutpakke-model (2026-11-10, efter Fürsters beslutning) – `tests/qa/test_qa_billing_minutpakker.py`

| Tilfælde | Forventet | Faktisk | OK | Test |
|---|---|---|---|---|
| 250 min indgående | 250 / 300 / 0 ekstra / 0 kr. | samme | ja | mp::one_package_level |
| + 61 min 1 s (62 påbegyndte) = 312 | 12 × 150 = 1.800; 251.300 / 62.825 / 314.125 | samme | ja | samme |
| Listen ændres (200 inkl., 3 kr.) efter aftale v1; september 310 min | 300 inkl., 10 ekstra, 1.500 | 200 inkl., 110 ekstra, 33.000 | **nej** F-BQ-011 | mp::package_terms_are_snapshotted |
| Fakturér oktober 310 min (fake Stripe) | linjer 249.500 + 1.500; 251.000 / 62.750 / 313.750; linjer frosset | samme | ja | mp::overage_reaches_the_stripe_invoice |
| Sen rapport: opkald 31/10 22:58Z, 5 min, efter fakturaen | 2.250 i alt (faktura + efterregistrering) | 1.500; 750 øre faktureres aldrig | **nej** F-BQ-012 | mp::usage_reported_after_the_month_was_invoiced |
| Faktureret periodes linjer i app / operatørens forbrugsvisning / tvist pr. opkald | – | ikke bygget | not-implemented | mp::… (xfail strict) |

## Privat-dybderunde fase 2 (PBQ, 2026-11-10) – `tests/qa/test_qa_pd_billing.py`, DB `qa_pd6`, kun fake Stripe

Forventet = uafhængige tabeller i testfilen (`EXPECTED_PLANS`, `EXPECTED_PACK`, `EXPECTED_LOCALE`, `EXPECTED_QUOTA`). Faktisk = `GET /privat/subscription?currency=`, `web/src/lib/prices.json` og Checkout-linjen sendt til Stripe. Øre inkl. moms.

### Planpriser – alle 4 valutaer × 3 planer (API = web-katalog = Stripe-linje)

| Valuta | Plan | Måned | År/md. | År i alt (=12×år/md.) | Rabat vs. måned | Opkald / personer | OK |
|---|---|---|---|---|---|---|---|
| DKK | Basis | 4.900 | 3.900 | 46.800 | 20,4 % | 3 / 1 | ja |
| DKK | Plus (Anbefalet) | 9.900 | 7.900 | 94.800 | 20,2 % | 10 / 1 | ja |
| DKK | Familie | 16.900 | 13.500 | 162.000 | 20,1 % | 25 / 5 (*F-PBQ-07*) | beløb ja · «5 personer» findes ikke |
| SEK | Basis / Plus / Familie | 6.900 / 14.900 / 24.900 | 5.500 / 11.900 / 19.900 | 66.000 / 142.800 / 238.800 | 20,3 / 20,1 / 20,1 % | som DKK | ja |
| NOK | Basis / Plus / Familie | 7.900 / 15.900 / 26.900 | 6.300 / 12.700 / 21.500 | 75.600 / 152.400 / 258.000 | 20,3 / 20,1 / 20,1 % | som DKK | ja |
| EUR | Basis / Plus / Familie | 649 / 1.349 / 2.249 | 519 / 1.079 / 1.799 | 6.228 / 12.948 / 21.588 | 20,0 / 20,0 / 20,0 % | som DKK | ja |

Præcis én «Anbefalet» (Plus) i alle valutaer. «Spar 20 %» er sandt (≥ 20,0 %) for alle 12. Stripe-testkataloget kan ikke nås fra sandkassen. DKK med `PRIVAT_STRIPE_PRICE_*` sætter `price`-id på linjen, og beløbet bag id'et skal tjekkes manuelt i Stripe Dashboard (test) mod tabellen.

### Checkout-linje pr. sprog (8 sprog × 3 planer × 2 intervaller = 48 kombinationer)

| Sprog | Valuta | Stripe-locale | Momssats på linjen (mode «danish») | unit_amount | OK |
|---|---|---|---|---|---|
| da | DKK | da | txr DK 25 % inkl. | måned eller år i alt fra tabellen | ja |
| en, de, es, fr, it | EUR | samme | txr DK 25 % inkl. | EUR-tabel | ja |
| sv | SEK | sv | txr DK 25 % inkl. | SEK-tabel | ja |
| no | NOK | **nb** | ingen (VOEC ikke registreret), tekst uden «moms» | NOK-tabel | ja |
| STRIPE_TAX_ENABLED=true (da, Familie år) | DKK | da | `automatic_tax.enabled`, tax_code txcd_10103000, ingen tax_rates, inclusive | 162.000 | ja |

Valuta er klæbende: første checkout (sv → SEK), anden checkout med de → stadig SEK. *Bemærk:* valutaen låses allerede ved **oprettet** checkout, ikke ved betaling, så en dansk bruger med engelsk UI låses til EUR (ikke indberettet, notér til qa-lead).

### Moms-split (inkl. 25 %, Stripes afrunding: moms = afrund(brutto × 0,25/1,25))

| Beløb | Netto | Moms | Eksakt? |
|---|---|---|---|
| Alle DKK/SEK/NOK planbeløb (18 stk.) | brutto/1,25 | brutto/5 | ja, eksakt i hele øre |
| EUR 649 / 1.349 / 2.249 | 519 / 1.079 / 1.799 | 130 / 270 / 450 | nej, afrundet (129,8 / 269,8 / 449,8) |
| EUR årsbeløb 6.228 / 12.948 / 21.588 | 4.982 / 10.358 / 17.270 | 1.246 / 2.590 / 4.318 | nej, afrundet |
| Kreditpakke DKK 2.900 | 2.320 | 580 | ja (= `PRIVAT_CREDIT_PACK_NET_MINOR`) |
| Kreditpakke EUR 399 | 319 | 80 | nej, afrundet (79,8) |

### Kreditpakke (10 credits)

| Tilfælde | Forventet | Faktisk | OK | Test |
|---|---|---|---|---|
| Pris DKK / SEK / NOK / EUR | 2.900 / 4.500 / 4.500 / 399 | 2.900 / 4.500 / 4.500 / 399 | ja | sub_21_credit_pack_once… |
| Afbrudt/unpaid session | +0 | +0 | ja | samme |
| Betalt, webhook x 2 (replay) | +10 én gang | +10, `duplicate: true` | ja | samme |
| Samme session via `async_payment_succeeded` | ingen ekstra | ignored | ja | samme |
| Betalt 1.450 med gyldig 50 %-kode (kodefelt vises) | +10 (eller intet kodefelt) | 0 credits, pengene trukket → efter rettelse: intet kodefelt (live :8400 bekræftet) | nej → **ja efter rettelse** | sub_21_paid_with_a_promotion_code… |
| Fuld refusion 2.900 | saldo 3 (velkomst) | **13** | **nej – F-PBQ-05 (S2)** | credit_pack_refund… |

### Abonnement – livscyklus

| Tilfælde | Forventet | Faktisk | OK |
|---|---|---|---|
| Checkout-payload | kort altid, adresse required, telefon, trial 14, metadata | som forventet | ja |
| Åben session (0002 / 9995 / 3DS afvist) | status none, 409 needs_plan, ingen velkomstmail | som forventet | ja |
| 2. checkout på samme konto efter brugt trial | ingen trial_period_days/trial_end, samme customer | som forventet | ja |
| Ny e-mail + samme kort | uafklaret | ny 14-dages trial | **needs-decision F-PBQ-02** |
| Aktiv kunde starter ny checkout | 409 | 409 `subscription_exists` (fix 21:12) | ja |
| To åbne checkouts gennemført | højst 1 live abonnement | **2 live, 14.800 øre/md. efter trial** | **nej – F-PBQ-01 (S0)** |
| – efter rettelsen 21:49 (`dup_canceled`), med trial | 1 live, intet trukket | 1 live | ja (07b grøn, afventer verifier) |
| – tilbagevendende kunde, ingen trial (begge betalt med det samme) | 1 live + dublettens 9.900 refunderet | 1 live, **ingen refusion** → efter rettelse: POST /refunds | nej → **ja efter 451d53b** (07c grøn) |
| Trial → active (Familie), replay, sen trialing | active/familie/25, duplicate, sen trialing ignored | som forventet | ja |
| Lokal trial udløbet uden webhook | expired, kladde, opkald = 3 credits, derefter 409 needs_plan | som forventet | ja |
| Opsig i trial | adgang til trial_end, derefter intet, ingen faktura | backend ja · UI siger «Derefter Plus til 99 kr./md.» | **UI nej – F-PBQ-04 (S2)** |
| past_due → canceled (payment_failed) | adgang i dunning, slut ved ended_at | som forventet (regression F-BQ-003) | ja |
| Basis → Plus md → Plus år → Familie år → Basis md | kvote 3/10/10/25/3, personer 1/1/1/5/1 | som forventet | ja · plan-apps forbliver (F-PBQ-06) |

### Kvote ved månedsskifte (Europe/Copenhagen)

| Godkendt (UTC) | Lokal | Ur (UTC) | Forventet calls_used | Faktisk | OK |
|---|---|---|---|---|---|
| 31/10 22:30 | 31/10 23:30 CET | 31/10 22:45 | 1 | 1 | ja |
| 31/10 22:30 | 31/10 23:30 CET | 31/10 23:00 (= 1/11 00:00 lokal) | 0 (nulstillet) | 0 | ja |
| 31/10 23:30 | 1/11 00:30 CET | 1/11 09:00 | 1 (november) | 1 | ja |
| 31/10 23:30 | 1/11 00:30 CET | 31/10 22:59 | 0 (oktober) | 0 | ja |
| 25/10 00:30 og 01:30 (DST-natten, 02:30 CEST/CET) | 25/10 | 30/10 | 1 hver | 1 | ja |
| 31/3/2027 21:30 | 23:30 CEST | 21:45 / 22:00 | 1 / 0 | 1 / 0 | ja |
| 31/3/2027 22:30 | 1/4 00:30 CEST | 1/4 08:00 | 1 (april) | 1 | ja |

Basis 3 opkald: ubesvaret og fejlet tæller ikke. 4. opkald = 3 credits reserveret. Replay af slutrapport ændrer intet (ledger netto 0 efter capture).

### Henvisninger / regninger / udgifter / fællesgave

| Tilfælde | Forventet | Faktisk | OK |
|---|---|---|---|
| Selvinvitation, samme invitee x 2, 11 nye med trial | 0, én gang, maks. 10 × 3 = 30 credits/md. | som forventet | ja |
| 3 gratis alt-konti (alias-e-mail) via F-PQ-03-aktivering | 0 | **+9 credits til inviter** | nej – konsekvens af F-PQ-03 (ingen dublet) |
| `parse_amount` «1.234,50 kr.» / «640» / «1.250» / «-5» | 123.450 / 64.000 / 125.000 / None | som forventet | ja |
| Forfald den 31. i feb 2027 / 2028; kvartal, halvår, år, once | 28/2, 29/2; rul korrekt; once ruller ikke | som forventet | ja |
| 100 kr. delt på 3 | 6.666 / −3.333 / −3.333, sum 0, 2 overførsler | som forventet | ja |
| Udlæg 0 / negativt | afvist (422) | afvist | ja |
| Fællesgave 1.000 kr.: 0/negativ, 400,01 over rest | 422; 409 `pledge_exceeds_remaining`, remaining 40.000 | som forventet | ja |

### Gentest efter 451d53b (22:3x)

| Fund | Gentest | Resultat |
|---|---|---|
| F-PBQ-01 dobbelt abonnement | pytest 07/07b + live :8400 (DELETE på dubletten, 3. checkout 409) | rettet, afventer verifier |
| F-PBQ-09 betalt dublet | pytest 07c (POST /refunds) | rettet, afventer verifier |
| F-PBQ-03 rabatkode på kreditpakke | pytest sub_21_no_promotion_codes + live (ingen allow_promotion_codes, 2.900) | rettet (ingen koder på pakken); underbetaling logges |
| F-PBQ-06 plan-apps efter udløb | ENT-02/03: gate afviser, data bevares, påmindelser stopper, kommer igen med plan | beslutning A implementeret |
| F-PBQ-07 Familie 5 personer | husstand: 4 medlemmer + ejer, 6. → household_full, fælles kvote 25, rettigheder følger ejerens plan | bygget |
| F-PBQ-04 / 05 / 02 / 08 | uændret | åbne |
