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
