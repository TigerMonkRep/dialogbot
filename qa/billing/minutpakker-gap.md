# Minutpakke-model – gap-analyse for C09, C15, M04, B03, B04, B05 (billing-qa, 2026-11-10)

**Beslutning (Fürster, 2026-11-10):** kravene om pakker udgår ikke. «Pakkerne er en del af konceptet, som indeholder x antal minutter inkluderet, og bruger man mere udover det, skal det selvfølgelig afregnes.» Fortolkning her: en pakke = abonnementets inkluderede minutter i en kalendermåned; forbrug ud over pakken afregnes pr. påbegyndt minut på månedsfakturaen.

**Hvad koden siger i dag (læst, ikke gættet):**
- Der er **ét niveau**: abonnement 2.495 kr./md. med **300 indgående minutter**, derefter 1,50 kr. pr. påbegyndt minut (`app/modules/billing/prices.py:18-22`). Inkluderede minutter er én global konstant; `markets.ERHVERV` har pris pr. valuta, men ingen minutkvote. `SalesOffer.package` findes med værdien `"reception"` (`app/models/sales.py:417`), men intet andet niveau.
- **Udgående kampagneminutter er ikke en del af pakken**: 4 kr. pr. opkald + 2 kr. pr. påbegyndt samtaleminut, altid (`prices.py`-docstring, `statement.py:48-60` udelukker kampagne-, demo- og ejerens testopkald fra indgående).
- Ingen overførsel af ubrugte minutter og ingen forholdsmæssig pakke ved start midt i en måned (`statement.py`-docstring: «No proration in this stage»).
- Forbrug faktureres bagud månedligt (`stripe.invoice_due`); der er ingen forudbetalt pakke, ingen ordre og intet at refundere ved annullering ud over kreditnota/refusion på en faktura.
- Teksten «300 minutters indgående opkald» er hårdkodet i `web/src/i18n/messages/*/site.json`, `landing.json` og `app.json` (`week.cost.note`, `help.leads.billing.a`) – kun Konto læser tallet fra API'et.

Status: **(a)** bygget og bevist af test · **(b)** bygget, men ikke synligt for brugeren eller ikke testet · **(c)** mangler · **fail** = bygget forkert (fund). Størrelse: S ≤ 1 dag, M 2–4 dage, L ≥ 1 uge.

Tests i denne kørsel: `tests/qa/test_qa_billing_minutpakker.py` (3 pass, 2 fail = fund, 3 xfail-strict = ikke bygget). Log: `qa/evidence/MINUTPAKKER/pytest-run-2026-11-10.log`. Øvrige henvisninger er eksisterende, grønne tests fra bølge 1 (`qa/billing/expected-vs-actual.md`).

## 1. Pakken selv (fælles for alle seks)

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| P1 | Ét niveau: 300 indgående min/md. inkluderet i 2.495 kr. | (a) | `test_qa_billing_minutpakker.py::test_mp_one_package_level_300_inbound_minutes_shown_as_used_of_included`; `test_qa_billing_x28.py::test_x28_inbound_boundaries_and_exactly_300_included` | – |
| P2 | Flere niveauer (x minutter pr. niveau, pris pr. niveau) | (c) | Én konstant, intet niveau-felt på aftale/tilbud ud over `package="reception"` | **Spørgsmål 1.** Ved ja: niveau-katalog (kode, versioneret), niveau på tilbud+aftale, valg på Konto/salg, parametriseret tekst (M) |
| P3 | Udgående kampagneminutter trækker ikke på pakken | (a) for kodens regel | `test_x28_campaign_calls_never_count_as_inbound_minutes` | **Spørgsmål 2** (bekræft). Ved «ja, de skal indgå»: fælles minutkvote, ny prisregel (M) |
| P4 | Overforbrug pr. påbegyndt minut, 1,50 kr.; grænser 0/1/59/60/61 s; 301. minut | (a) | `test_x28_inbound_boundaries_and_exactly_300_included`; `tests/test_billing_statement.py::test_inbound_minutes_above_the_included_300_are_charged` | Brøkdelssekunder (60,4 s) er fortsat needs-decision **F-BQ-001** |
| P5 | Kvoten nulstilles ved kalendermåned i Europe/Copenhagen (midnat, sommertid, nytår) | (a) | `test_x28_included_minutes_reset_at_copenhagen_midnight_month_change`, `test_x28_dst_start_month_boundary_and_new_year` | – |
| P6 | Ejerens testopkald og demo-opkald trækker ikke på pakken | (a) demo / (b) testopkald | `test_billing_statement.py` (DemoCall); `TelephonyTest` udelukkes i `statement.py:52`, ingen test | Regressionstest for testopkald (S) |
| P7 | Dobbelt slutrapport tælles én gang | (a) | `provider_call_id` unik (`domain.py:632`); `test_x28_duplicate_end_of_call_report_is_priced_once` | – |
| P8 | Start midt i måneden / ubrugte minutter overføres ikke | (b) dokumenteret regel, ikke vist for kunden | `statement.py`-docstring | Én linje på Konto/priser: «minutterne gælder kalendermåneden og overføres ikke» (S) |

## 2. B05 – periode-/abonnementsopgørelse (tidligere «ordre»)

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| B05.1 | Månedspris snapshottes pr. aftaleversion; listeprisændring rører ikke gamle måneder | (a) | `test_qa_billing_b05.py::test_b05_agreement_price_snapshot_is_immutable_under_a_list_price_change` | – |
| B05.2 | Pakkens indhold (inkl. minutter) og overforbrugspris snapshottes pr. aftaleversion | **fail** | **F-BQ-011-B05**; `test_mp_package_terms_are_snapshotted_per_agreement_not_read_from_the_list_price` (200/110/33.000 i stedet for 300/10/1.500) | Kolonner på `reception_agreements`, udfyldt fra tilbud/liste, backfill 300/150; statement + `agreements.out` læser aftalen (M) |
| B05.3 | Kampagnepriser snapshottes (pr. kampagne/opkald) | (a) | `test_x28_price_snapshot_survives_a_list_price_change` | – |
| B05.4 | Løbende forbrug: brugt / inkluderet / over / beløb | (b) | API: `test_mp_one_package_level…` (250/300/0 → 312/12/1.800; totaler 251.300/62.825/314.125). UI: `konto/page.tsx:121-123` viser brugt «af 300» og overforbrug – ingen browsertest; «tilbage» vises ikke eksplicit; kun ejer/admin | Vis «x min tilbage», e2e-test af Konto i tre tilstande: under / præcis 300 / over (S) |
| B05.5 | Overforbrug står på fakturaen (beskrivelse + beløb) og perioden fryses | (a) | `test_mp_overage_reaches_the_stripe_invoice_and_the_invoice_keeps_the_period_snapshot` (Stripe-linjer 249.500 + 1.500, faktura 251.000/62.750/313.750, `invoices.lines` frosset) | – |
| B05.6 | Kunden kan se en faktureret periodes pakkeforbrug i appen | (c) | `test_mp_customer_can_read_the_frozen_package_usage_of_an_invoiced_month` (xfail): `invoice_out` udelader `lines`; Konto viser kun indeværende måned + Stripe-link | `lines` i `GET /billing/invoices` + periodevisning (måned-vælger eller fakturadetalje `/app/billing/orders/:month`) (M) |
| B05.7 | Relateret faktura og refusions-/kreditnotahistorik pr. periode | (b) | `invoices.refunds` udfyldes af webhooks (`test_qa_billing_b06.py`), men vises ikke; **F-BQ-008** (dobbelt/forkert provision ved delrefusion) åben | Vis refusioner/kreditnotaer på periodevisningen (S, efter B05.6) |
| B05.8 | DB-012 net/moms/brutto adskilt, half-up | (a) ren regel | `test_b05_db012_net_tax_gross_are_separate_and_half_up` (562.500 / 225.000) | Tallene gælder de gamle kampagnepakker; behold som regressionsregel |

## 3. C15 – kampagneafstemning

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| C15.1 | Opkald, samtaleminutter og beløb pr. kampagne pr. måned fra samme kilde som opgørelsen | (a) | `test_qa_billing_db001_db003.py::test_db003_contacts_and_attempts_are_separate_and_consistent_with_the_statement` (301 kontakter, 420 opkald, 168.000) ; `test_qa_c15.py::test_c15_counters_from_one_source` | – |
| C15.2 | «Købt/forbrugt/ubrugt/afventende pakker» | udgår for kampagner | Kampagneminutter er ikke pakkeforbrug (P3). `test_c15_c09_packages_checkout_and_refunds_exist` (xfail) tester den gamle model | Ved svar «nej» på spørgsmål 2: omskriv xfail-testen til C15.3–C15.5 (S) |
| C15.3 | Afventende: opkald uden slutrapport vises som afventende, ikke som 0 min | (c) | `statement._minutes_of` tæller manglende rapport som 0; ingen markering | `pending_reports` i kampagne- og månedsopgørelse (S) |
| C15.4 | Sent forbrug efter månedsafslutning faktureres (afstemning) | **fail** | **F-BQ-012-M04**; `test_mp_usage_reported_after_the_month_was_invoiced_is_billed_somewhere` (750 øre tabt) | Henstand + «efterregistreret forbrug»-linje (M) |
| C15.5 | Annullering/stop: ingen forudbetaling → intet at refundere; refusion kun som kreditnota på faktura (afventer/bekræftet af Stripe) | (b) | Pause findes (ingen stop-/annullerrute i `campaigns/router.py`); refusionswebhooks i `test_qa_billing_b06.py`; ingen kampagnevisning af refusion | Tekst på kampagnesiden + link til periodevisning (S) |

## 4. C09 – kampagnestart / betaling

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| C09.1 | Omkostningsoversigt før start: priser, maks.-beløb netto/moms/brutto | (a) API, (b) UI | `test_qa_c15.py::test_c15_campaign_does_not_claim_packages` (`max_cost`); `kampagner/client.tsx:175-177` viser maks. netto/brutto; ingen browsertest af beløbene | e2e-test af start-dialogens tal (S) |
| C09.2 | Prisændring siden visning afviser start; start kun ved eksplicit bekræftelse | (a) | `tests/test_campaigns.py::test_start_is_explicit_and_honest`; `test_qa_c11.py::test_c11_launch_needs_explicit_confirmation_and_capability` (`accept_max_net_minor`, `price_changed`) | – |
| C09.3 | Betaling starter aldrig kampagnen | (a) | Samme tests; ingen betalingssti kalder start | – |
| C09.4 | Betalingsstatus (behandles / kræver handling / lykkedes / fejlede) | (b) på månedsfakturaen, ikke pr. kampagne | Fakturastatus + rykker: `test_b06_states_open_paid_failed_void_and_download_links`; **F-BQ-007** (sen payment_failed) åben | Ingen kampagne-checkout i denne model; vis fakturastatus på Konto (findes). Ingen ny skærm |
| C09.5 | Betalingskort på kontoen før første kampagnestart | (c) | `campaigns/router.py` start tjekker ikke `BillingAccount.payment_method_id` | Kræv kort (eller operatør-undtagelse) før start, så forbrug ikke kan opstå uden betalingsmiddel (S) |

## 5. M04 – operatørens overblik

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| M04.1 | Priskatalog: listepris, pakke(r), overforbrugspris, kampagnepriser, pr. valuta, med version | (c) | Kun i kode; `test_qa_m04.py::test_m04_billing_admin_exists` (xfail) | Læsevisning af `prices.py`/`markets.ERHVERV` + versionsdato (S). Redigerbart katalog kun hvis P2 = flere niveauer (M) |
| M04.2 | Pr. kunde: aftaleversion og snapshot, månedens forbrug (brugt/inkl./over, kampagneopkald/-min) | (c) | `test_mp_operator_sees_package_usage_per_customer` (xfail): `/operator/admin/customers/{id}` har ingen `agreement`/`usage` | Genbrug `statement()` i kundedetaljen (S) |
| M04.3 | Pr. kunde: fakturaer med status og beløb | (b) | `admin/router.py` kundedetalje (måned, status, brutto, nummer); `test_m04_operator_customer_view_is_operator_only` tjekker kun nøgler og adgang | Vis frosne linjer + refusioner; test beløb (S) |
| M04.4 | Tværgående: fejlede fakturaer / rykkere | (b) | `admin/router.py` overview `bad_invoices` (5 seneste); ingen test | Test + liste med alle `payment_failed/failed` (S) |
| M04.5 | Månedlig afstemning: frossen faktura vs. ny opgørelse, sent forbrug | (c) | Se **F-BQ-012-M04** | Afstemningsvisning med afvigelser pr. kunde/måned (M) |
| M04.6 | Tvister og autoriseret refusion/kreditnota (fire-øjne, audit) | (c) | Ingen tvist-/refusionsruter; DB-002-regel kun som ren funktion | Se B04 (L) |
| M04.7 | DB-004: reception og kampagne holdes adskilt pr. kunde | (a) delvist | `test_m04_operator_customer_view_is_operator_only` (separate `calls`/`campaigns`) | – |

## 6. B03 – forbrugsregister (tidligere «billable-lead register»)

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| B03.1 | Godkendte henvendelser koster intet under abonnementet; gamle model-B-gebyrer bevares | (a) | `test_qa_billing_b03.py::test_b03_approval_under_the_subscription…`, `test_b03_legacy_model_b_fee_snapshot_survives_a_new_agreement`; DB-001 `test_db001_model_a_ignores_leads_model_b_charges_them` (599.500 / 658.600) | – |
| B03.2 | Register pr. opkald: tidspunkt (Europe/Copenhagen), varighed, påbegyndte minutter, om det ligger i pakken eller er overforbrug | (c) | Opkaldsloggen viser opkald, men ingen faktureringsklassifikation; statement er kun en sum | `billing_minutes` + `in_package/overage` pr. opkald i opkaldslisten/eksport (M) |
| B03.3 | Dubletstatus: samme opkald tælles én gang | (a) | `provider_call_id` unik; `test_x28_duplicate_end_of_call_report_is_priced_once` | – |
| B03.4 | Indgang til tvist pr. opkald | (c) | `test_mp_failed_call_minutes_can_be_disputed_or_credited` (xfail); `test_b03_register_route_and_dispute_api_exist` (xfail) | Knap «Bestrid opkald» på opkaldsdetalje → tvist (M, sammen med B04) |
| B03.5 | Fejlopkald (teknisk fejl hos Dialogbot) trækker ikke på pakken | (c) | `statement.inbound_minutes` filtrerer ikke på `ended_reason`; et opkald, der dør i vores pipeline efter 40 s, koster 1 minut af pakken | **Spørgsmål 3.** Automatisk udelukkelse af egne fejlårsager (S) eller kun via tvist (B04) |

## 7. B04 – tvist og kreditering i minutmodellen

| # | Delkrav | Status | Evidens | Forslag (str.) |
|---|---|---|---|---|
| B04.1 | Tvist med årsag/evidens, afventer behandling, afgørelse (godkend/afvis), audit | (c) | `test_b04_already_invoiced_branch_and_dispute_records_exist` (xfail) | Model `billing_disputes` (opkald/linje, årsag, status, besluttet af/hvornår) (M) |
| B04.2 | Ikke-faktureret måned: godkendt tvist fjerner minutterne fra pakkeforbruget før fakturering, ingen kreditnota; afvist tvist ændrer intet | (c) for minutter; (a) for legacy-leads | DB-002-tal for leads: `test_b03_db002_unbilled_dispute_rule_numbers`, `test_b04_db002_neither_ruling_creates_a_credit_note_or_changes_money_twice` (208.600/14.900, 223.500/14.900, ingen kreditnota) | Statement trækker godkendte tvistminutter fra; minutter går tilbage i pakken, beløb genberegnes (S efter B04.1) |
| B04.3 | Allerede faktureret: kreditnota hos Stripe på differencen (net/moms/brutto), godkendt af operatør, idempotent ved webhook-replay | (c) | Webhooks for `credit_note.created`/`charge.refunded` findes (`test_qa_billing_b06.py`), men ingen sti der opretter dem; **F-BQ-008** åben | Kreditnota via Stripe test mode med idempotency-key pr. tvist; regressionstal efter DB-012-mønster (M) |
| B04.4 | Kunden ser afgørelse og evt. kreditnota | (c) | – | Status på opkald og periodevisning; mail ved afgørelse (S) |

## Spørgsmål Fürster skal besvare (koden kan ikke svare)

1. **Niveauer:** Er der kun én pakke (2.495 kr./md. med 300 indgående minutter), eller skal der være flere niveauer? Hvis flere: antal minutter og månedspris pr. niveau, og er overforbrugsprisen (1,50 kr./påbegyndt min) den samme på alle niveauer?
2. **Udgående minutter:** Skal udgående kampagneminutter trække på pakkens minutter, eller forbliver kampagner som i dag 4 kr. pr. opkald + 2 kr. pr. påbegyndt minut uden for pakken (som hjemmesiden siger)?
3. **Fejlopkald:** Når et indgående opkald afbrydes af en teknisk fejl hos Dialogbot, skal minutterne så automatisk ikke tælle i pakken, eller kun hvis kunden bestrider opkaldet?

Antagelser indtil svar (fra prisreglerne, ikke gættet): ubrugte minutter overføres ikke; ingen forholdsmæssig pakke ved start midt i måneden; pakken gælder kalendermåneden i Europe/Copenhagen.

## Rækkefølge (forslag)

1. F-BQ-011 (snapshot af pakke på aftalen) og F-BQ-012 (henstand + efterregistreret forbrug) – penge, M+M.
2. B05.4/B05.6 + M04.2 – synligt forbrug for kunde og operatør, S+M+S.
3. B03.2/B04 – register, tvist og kreditnota, L samlet.
4. P2/P3 efter Fürsters svar.
