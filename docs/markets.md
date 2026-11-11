# Markeder: valuta, priser og moms

Kilden er `app/modules/billing/markets.py` – den eneste fil, hvor en udenlandsk pris står. De danske priser i
`app/modules/billing/prices.py` er udgangspunktet; de andre valutaer er afrundede listepriser (ikke dagskurser – en pris
flytter sig ikke med valutakursen). Websitet læser den genererede `web/src/lib/prices.json`
(`python -m scripts.export_prices web/src/lib/prices.json`); CI fejler, hvis filen afviger fra `markets.py`.

## Prisliste

Beløbene er skrevet med `markets.fmt` (samme visning som på fakturalinjerne).

| Erhverv (ekskl. moms) | DKK | SEK | NOK | EUR |
|---|---|---|---|---|
| Abonnement pr. md. | 2.495 kr. | 3 695 kr | 3 995 kr | €329 |
| Kampagneopkald (pr. opkald) | 4 kr. | 5,90 kr | 6,30 kr | €0.55 |
| Kampagne, pr. påbegyndt samtaleminut | 2 kr. | 2,95 kr | 3,15 kr | €0.27 |
| Indgående minut ud over 300 | 1,50 kr. | 2,20 kr | 2,35 kr | €0.20 |
| Specialist-opsætning (én gang) | 5.000 kr. | 7 295 kr | 7 895 kr | €669 |

| Privat (inkl. moms) | DKK | SEK | NOK | EUR |
|---|---|---|---|---|
| Basis – månedlig | 49 kr. | 69 kr | 79 kr | €6.49 |
| Basis – årlig, pr. md. | 39 kr. | 55 kr | 63 kr | €5.19 |
| Basis – årlig, i alt | 468 kr. | 660 kr | 756 kr | €62.28 |
| Plus – månedlig | 99 kr. | 149 kr | 159 kr | €13.49 |
| Plus – årlig, pr. md. | 79 kr. | 119 kr | 127 kr | €10.79 |
| Plus – årlig, i alt | 948 kr. | 1 428 kr | 1 524 kr | €129.48 |
| Familie – månedlig | 169 kr. | 249 kr | 269 kr | €22.49 |
| Familie – årlig, pr. md. | 135 kr. | 199 kr | 215 kr | €17.99 |
| Familie – årlig, i alt | 1.620 kr. | 2 388 kr | 2 580 kr | €215.88 |
| Ekstra opkald – besvaret | 5 kr. | 7,38 kr | 7,88 kr | €0.69 |
| – telefonsvarer | 1,25 kr. | 1,88 kr | 2 kr | €0.18 |
| – ubesvaret/optaget | 0,31 kr. | 0,44 kr | 0,50 kr | €0.04 |
| – pr. påbegyndt minut (besvaret) | 2,50 kr. | 3,69 kr | 3,94 kr | €0.34 |
| – højst pr. opkald (reserveres) | 17,50 kr. | 25,81 kr | 27,56 kr | €2.39 |
| Opkaldssaldo – optankning | 50 kr. / 100 kr. / 200 kr. | 74 kr / 148 kr / 295 kr | 79 kr / 158 kr / 315 kr | €7 / €14 / €27 |
| Velkomstbonus / henvisning (hver) | 10 kr. | 14,75 kr | 15,75 kr | €1.35 |
| Ekstra opgave | 3 kr. | 4,43 kr | 4,73 kr | €0.41 |

Ekstra opkald (beslutning 2026-11-11, F-PDEC-01): Erhvervs nettopris pr. udfald i markedets valuta × 1,25 (Privats regel:
dansk moms, samme bruttopris i hele valutaen), half-up til hele øre/öre/cent (`markets.privat_extra_call`). Optankning,
bonusser og ekstra opgave: DKK-beløbet × markedets faktor (Erhvervs minutpris: SEK 1,475, NOK 1,575, EUR 0,135) –
optankninger afrundet til hele kroner/euro, resten til hele øre (`markets.privat_from_dkk`). De udenlandske optankninger
og bonusser er afledt, ikke besluttet (se F-PDEC-01). Opkaldssaldoen føres i kontoens valuta (`credit_ledger.currency`);
en DKK-velkomstbonus flyttes én gang til kontoens valuta ved første Checkout i en anden valuta (`ledger.adopt_currency`).

## Hvilken valuta en kunde betaler i

**Erhverv**

- Virksomhedens land (`BusinessProfile.country`): DK → DKK, SE → SEK, NO → NOK, alle andre → EUR
  (`markets.currency_for_country`).
- **Valutaen låses af den første aftale.** `agreements.create` gemmer valuta og pris på aftalen; alle senere versioner
  arver aftalens valuta, også hvis landet bagefter ændres (prisen er så listeprisen i den låste valuta). Før der er en
  aftale, følger valutaen landet.
- En aftale fra Dialogbots eget salg (accepteret `SalesOffer`) er altid DKK. Den interne salgskanal
  (`sales/outbound.py`) er og bliver DKK.
- Kundekampagner snapshotter opkalds- og minutprisen i arbejdsrummets valuta, når kampagnen oprettes.
- Månedsoversigten er i den gældende aftales valuta (uden aftale: arbejdsrummets). Linjeteksterne er danske for DKK og
  engelske for de andre valutaer. En rabatkode med et fast beløb er i DKK og kan kun bruges af DKK-kunder
  (`422 discount_currency_mismatch`); procentkoder virker i alle valutaer.

**Privat**

- Den besøgendes sprog ved Checkout: da → DKK, sv → SEK, no → NOK, en/de/es/fr/it → EUR
  (`markets.currency_for_locale`). Klienten sender `locale` på `POST /privat/subscription/checkout` og
  `POST /privat/balance/checkout`.
- Valutaen gemmes på `private_subscriptions.currency` ved første Checkout, og kunden beholder den (webhooken spejler den
  valuta, Stripe faktisk opkræver i). Eksisterende rækker uden valuta læses som DKK.
- `GET /privat/subscription?currency=EUR` viser planerne i rækkens valuta, ellers den ønskede, ellers DKK.
- Faste Stripe-pris-id'er (`PRIVAT_STRIPE_PRICE_*`) er DKK-priser og bruges kun til DKK; andre valutaer får inline
  `price_data`.

## Moms

To veje, styret af `STRIPE_TAX_ENABLED`:

### `STRIPE_TAX_ENABLED=true` – Stripe Tax afgør momsen

- **Erhverv-fakturaer**: `automatic_tax: {enabled: true}`, hver linje har skattekoden `txcd_10103001` (SaaS, erhverv)
  og `tax_behavior: exclusive`; ingen egne skattesatser og ingen egen note. Stripe-kunden har virksomhedens adresse og
  momsnummeret som kunde-skatte-id (`eu_vat` i EU, `no_vat` i Norge), så Stripe Tax selv anvender omvendt betalingspligt
  og skriver sin egen note. Fakturarækken (`invoices`) tager netto/moms/brutto fra Stripes færdige faktura
  (`total_excluding_tax`, `total_taxes`, `total`) og har `tax_source = "stripe_tax"`.
- **Privat Checkout** (abonnement og optankning af Opkaldssaldoen): `automatic_tax: {enabled: true}`, prisen er `tax_behavior: inclusive`,
  produktet har skattekoden `txcd_10103000` (SaaS, privat), faktureringsadressen er påkrævet, og en eksisterende kunde
  får `customer_update: {address: "auto", name: "auto"}`. Et fast Stripe-pris-id (kun DKK) skal selv have
  skattekoden på sit produkt i Stripe.
- Et EU-firma uden for Danmark skal stadig have givet sit momsnummer, før kort gemmes og fakturaer laves
  (`409 vat_number_required`) – uden det ville Stripe Tax behandle det som en forbruger.
- Månedsoversigten viser fortsat vores eget **skøn** (`vat.source = "estimate"`); den opkrævede moms står på fakturaen.

### `STRIPE_TAX_ENABLED=false` (standard) – vores egne regler

Reglerne i `markets.py` (bekræft med revisor før første udenlandske salg):

**Erhverv (B2B)**, faktureres månedsvis bagud – `markets.erhverv_vat(country, vat_number)`:

| Virksomhed | Moms | `vat.kind` | På fakturaen |
|---|---|---|---|
| Danmark | 25 % dansk moms | `domestic` | Stripe-skattesatsen «Moms» 25 % (eksklusiv, metadata `dk_vat_25`) |
| Andet EU-land, med momsnummer | 0 – omvendt betalingspligt (art. 196) | `reverse_charge` | Ingen skattesats; noten i sidefod og som custom field |
| Andet EU-land, uden momsnummer | – | `vat_number_required` | Kan ikke gemme kort (`409 vat_number_required`) eller faktureres; oversigten vises som forhåndsvisning med sats 0 |
| Uden for EU (Norge, USA …) | 0 – ikke dansk moms | `outside_eu` | Ingen skattesats; noten i sidefod og som custom field |

**Privat (B2C)**, priserne er inkl. moms og den samme bruttopris i alle lande med samme valuta –
`markets.privat_vat(country, eu_mode, voec_registered)`. Checkout får én inklusiv Stripe-skattesats (`tax_rates` på
linjen), valgt efter det land sproget peger på (`markets.LOCALE_COUNTRY`; `en` → danske regler):

- `PRIVAT_EU_VAT_MODE=danish` (standard): 25 % dansk moms for alle EU-forbrugere. Tilladt så længe Dialogbots
  grænseoverskridende B2C-salg i EU er under 10.000 EUR om året.
- `PRIVAT_EU_VAT_MODE=destination`: forbrugerens eget lands sats (kræver OSS-registrering hos Skattestyrelsen).
- Norge: ingen moms før VOEC-registrering; med `NO_VOEC_REGISTERED=true` 25 % norsk moms.
- Andre lande uden for EU: ingen moms (ingen skattesats på linjen).

Stripes `dynamic_tax_rates` (sats valgt efter faktureringsadressen) bruges ikke: den er udfaset, findes ikke længere i
det aktuelle Checkout-API, har aldrig understøttet Norge, og i `danish`-tilstand ville en DK-sats ikke matche en tysk
adresse. Derfor én fast sats efter sproget.

Skattesatser oprettes i Stripe ved første brug og genbruges via metadata `dialogbot=<land>_vat_<bp>_<incl|excl>`
(den oprindelige danske 25 % eksklusive sats beholder `dk_vat_25`).

### Indstillinger

| Variabel | Standard | Betydning |
|---|---|---|
| `STRIPE_TAX_ENABLED` | `false` | `true`: Stripe Tax afgør al moms (se ovenfor). Kun efter Stripe Tax er aktiveret i kontoen – ellers afviser Stripe `automatic_tax`. |
| `PRIVAT_EU_VAT_MODE` | `danish` | Kun uden Stripe Tax: `danish` = 25 % dansk moms til EU-forbrugere; `destination` = forbrugerens lands sats (kræver OSS). |
| `NO_VOEC_REGISTERED` | `false` | Kun uden Stripe Tax: `true` = 25 % norsk moms på norske forbrugere (efter VOEC-registrering). |

## Momsnummer (Erhverv)

`PUT /api/v1/workspaces/{ws}/billing/vat-number` `{"vat_number": "SE 5566 7788 9901"}` (`billing.manage`):
mellemrum, punktummer og bindestreger fjernes, store bogstaver; i EU skal præfikset passe til virksomhedens land
(Grækenland: `EL`), og et nummer uden præfiks får det; Norge gemmes som `123456789MVA`. Tom streng fjerner nummeret.
Fejl: `422 invalid_vat_number`, `422 vat_number_country_mismatch`. Audit `billing.vat_number_changed`. Har
arbejdsrummet en Stripe-kunde, skiftes kundens skatte-id med det samme (ellers inden næste kort/faktura).

## Stripe Tax setup (før `STRIPE_TAX_ENABLED=true`)

Stripe Tax er en betalt Stripe-funktion (gebyr pr. transaktion) – det er valgt bevidst.

1. Stripe Dashboard → **Tax** → aktivér Stripe Tax (først i test mode, så i live mode).
2. **Origin address**: Abildgade 18, 8200 Aarhus, Danmark.
3. **Default tax code**: Software as a service (SaaS) – business use (`txcd_10103001`). Koden sendes alligevel på hver
   linje (Erhverv `txcd_10103001`, Privat `txcd_10103000`).
4. **Default tax behavior**: Erhverv-priser er *exclusive*, Privat-priser *inclusive* – koden sender `tax_behavior` på
   hver linje, så standarden betyder kun noget for priser oprettet i dashboardet (fx `PRIVAT_STRIPE_PRICE_*`, som skal
   være *inclusive* og have skattekoden `txcd_10103000` på produktet).
5. **Registrations**: tilføj kun de registreringer, Dialogbot faktisk har – Danmark nu; EU OSS, når den er registreret
   hos Skattestyrelsen; Norge VOEC, når den er registreret. Stripe Tax overvåger tærsklerne og opkræver kun moms, hvor
   der er en registrering.
6. Sæt `STRIPE_TAX_ENABLED=true` på **begge** Render-tjenester (`dialogbot-api-staging` og
   `dialogbot-worker-staging` – workeren laver månedsfakturaerne) og deploy.
7. Kontrollér en testfaktura til en dansk, en tysk (med momsnummer) og en norsk virksomhed, og en Privat-Checkout med
   en tysk adresse.

## Før det første udenlandske salg

- [ ] Revisor har bekræftet reglerne ovenfor (B2B omvendt betalingspligt, Norge uden for EU, B2C i `danish`-tilstand).
- [ ] Beslutning om OSS: bliv i `danish`, så længe B2C-salg til andre EU-lande er under 10.000 EUR/år – ellers
  OSS-registrering hos Skattestyrelsen og `PRIVAT_EU_VAT_MODE=destination` (eller registreringen i Stripe Tax).
- [ ] Beslutning om VOEC: registrering i Norge, før salg til norske forbrugere passerer 50.000 NOK/år, og så
  `NO_VOEC_REGISTERED=true` (eller registreringen i Stripe Tax).
- [ ] Stripe: fakturaer viser kundens momsnummer (kunde-skatte-id `eu_vat`/`no_vat`) og Dialogbots CVR i sidefoden;
  overvej at tilføje Dialogbots eget DK-momsnummer som *account tax id* i Stripe, så det står på fakturaerne.
- [ ] Stripe Tax: følg «Stripe Tax setup» ovenfor, hvis Stripe skal afgøre momsen.
- [ ] Bogføring: fakturaer i SEK/NOK/EUR skal omregnes til DKK i bogføringen (Stripe udbetaler i kontoens valuta).

## Kendte begrænsninger

- Ambassadørprovision beregnes af fakturaens netto i fakturaens valuta (ingen omregning til DKK endnu).
- Privat-rabatkoder med fast beløb er Stripe-kuponer i DKK og kan ikke bruges på en Checkout i en anden valuta;
  procentkoder virker overalt.
