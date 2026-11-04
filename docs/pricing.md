# Priser – ét tilbud

Gældende fra 30. oktober 2026 (kampagneminutter og inkluderede indgående minutter tilføjet; 28. oktober: specialist-opsætning). Alle priser er ekskl. moms (25 % lægges på fakturaen).

| | Pris |
|---|---|
| **Abonnement** | **Fra 2.495 kr./md.** – telefon, chat, booking, opsummering af hver henvendelse. Ingen pris pr. henvendelse. **300 påbegyndte minutters indgående opkald pr. kalendermåned er med.** |
| **Indgående minutter ud over de 300** | **1,50 kr. pr. påbegyndt minut** – afregnes på månedens faktura som egen linje. Kampagne- og demo-opkald tæller ikke som indgående. |
| **Udgående kampagneopkald** | **4 kr. pr. udgående opkald + 2 kr. pr. påbegyndt samtaleminut** – hvert opkald, der ringes, tæller, også et nyt forsøg; minutterne afregnes, når opkaldsrapporten kommer. Ubesvaret = 4 kr.; 3 minutters samtale = 10 kr. |
| Opsætning – gør det selv | Med i abonnementet: byggevejledningens tre trin, cirka en halv time. |
| **Opsætning fra vores specialister** | **5.000 kr.** én gang – skræddersyet opsætning og integration til kundens egne systemer og behov (kalender, CRM, bookingsystem, viden og priser, stemmetræning, test før tænd). Accepteres den via et salgstilbud, kommer den automatisk på første faktura (linjen `setup_fee`, måneden hvor aftalen blev oprettet); ellers faktureres den manuelt. `SPECIALIST_SETUP_NET_MINOR` i `prices.py` er tallet. |
| Binding | Ingen. Opsigelse til udgangen af måneden. |

Tidligere fandtes to modeller (1.495 kr./md. eller 149 kr. pr. godkendt henvendelse) og kampagnepakker à 9 kr. pr.
kontakt. De findes ikke mere.

## Dialogbot Privat – abonnement (priser inkl. 25 % moms)

Gældende fra 4. november 2026. Private kunder: 14 dages gratis prøveperiode med Plus-rettigheder (uden kort), derefter vælger man selv.
Credits (10 for 29 kr.) findes stadig som «ekstra opkald», når månedens opkald er brugt (3 credits pr. besvaret opkald, uændret).

| Plan | Pr. måned | Pr. måned ved årlig betaling (betales årligt) | Opkald/md. | Personer | Alle apps i Butikken |
|---|---|---|---|---|---|
| Basis | 49 kr. (4900 øre) | 39 kr. (46.800 øre/år) | 3 | 1 | nej |
| **Plus** (anbefalet) | 99 kr. (9900 øre) | 79 kr. (94.800 øre/år) | 10 | 1 | ja |
| Familie | 169 kr. (16.900 øre) | 135 kr. (162.000 øre/år) | 25 | 5 | ja |

- Lister og påmindelser: ubegrænsede i prøveperioden og på alle planer. Uden plan (udløbet prøveperiode): 10 gratis opgaver/md. og
  credits som før.
- Opkald trækkes af planens kvote pr. kalendermåned (Europe/Copenhagen); et opkald, som ingen tager, eller som fejler, tæller ikke.
  Når kvoten er brugt: 3 credits pr. opkald (den eksisterende logik).
- Apps i Butikken med `included_in` (Kalender, Pakker og de kommende) kræver prøveperiode, Plus eller Familie; «Ring for mig» er med i
  alle planer. Delte lister og ønskelister er gratis for alle.
- Opsigelse og skift: Stripe Billing Portal. Ingen binding.
- **Kode:** `app/modules/billing/prices.py` – `PRIVAT_PLANS` (øre inkl. moms) og `PRIVAT_TRIAL_DAYS`; `app/modules/privat/subscriptions.py`
  læser dem, og `GET /privat/subscription` leverer kataloget til web (docs/privat-api.md), så web hardcoder ingen priser.
  Stripe: inline `price_data` (tax_behavior inclusive) eller faste price-id'er via `PRIVAT_STRIPE_PRICE_<PLAN>_<INTERVAL>`.

## Rabatkoder (operatører laver dem under Admin → Rabatkoder)

Én tabel (`discount_codes`), to veje ind. Koden er A-Z/0-9, 3-20 tegn, gemmes med store bogstaver; den gælder, når den er aktiv,
inden for sit tidsvindue og under sit maks. antal. `discount_redemptions` husker, hvilket arbejdsrum der brugte hvilken kode (én gang pr.
arbejdsrum). Kode: `app/modules/billing/discounts.py`.

- **Erhverv:** ejeren skriver koden under Konto → Abonnement («Har du en rabatkode?», `PUT /workspaces/{id}/billing/discount`). Fra
  den måned står der en negativ linje `discount_code` på månedsoversigten og dermed på Stripe-fakturaen: *én gang* = den første måned,
  *et antal måneder* = så mange måneder fra den måned, *altid* = hver måned. Procent regnes af månedens positive linjer; et beløb er
  ekskl. moms og aldrig mere end måneden. Én kode pr. arbejdsrum (409 ellers).
- **Privat:** planen betales gennem Stripe Checkout, så en kode til Privat/begge spejles til en Stripe-coupon + promotion code, når
  den oprettes (`stripe_coupon_id`, `stripe_promotion_code_id`; kræver `STRIPE_SECRET_KEY`). Checkout-siden viser Stripes eget felt
  «Tilføj rabatkode» (`allow_promotion_codes`), eller koden sættes på forhånd, når kunden kommer med den: feltet i planvælgeren eller
  et link `dialogbot.app/privat/konto?plan=plus&kode=KODEN` (`discounts=[{promotion_code}]`). Den færdige Checkout-session fortæller,
  hvilken promotion code der blev brugt, og det bliver brugen i `discount_redemptions`. Et beløb er her inkl. moms, som planpriserne.
- Deaktivering stopper koden (også hos Stripe); kunder, der allerede har brugt den, beholder rabatten.

## Hvor tallene bor

- **Kode:** `app/modules/billing/prices.py` – `SUBSCRIPTION_MONTHLY_NET_MINOR` (249.500 øre), `CAMPAIGN_CALL_NET_MINOR`
  (400 øre), `CAMPAIGN_MINUTE_NET_MINOR` (200 øre), `INBOUND_INCLUDED_MINUTES` (300), `INBOUND_EXTRA_MINUTE_NET_MINOR`
  (150 øre) og `SPECIALIST_SETUP_NET_MINOR` (500.000 øre). Prisaftalen, kampagner, Peters salgsmanuskript og testene læser dem derfra.
- **Tekster** (skal rettes i hånden, når prisen ændres): `web/src/app/priser`, `byggevejledning`, forsiden
  (`(public)/page.tsx`, inkl. strukturerede data), `ai-receptionist`, `chatbot`, `ai-telefonsvarer`, `vilkaar`,
  `proev-chat.tsx`, `app/modules/assistant/guide.md` (assistenten i appen), `web/public/llms.txt`, `web/public/materiale/*.html`, `app/modules/social/topics.py`
  (`FACTS`, `ALLOWED_AMOUNTS`) og `design-reference/byggevejledning`.
- `tests/test_prices.py` fejler, hvis en gammel pris eller "model A/B" dukker op igen i disse tekster.

## Sådan afregnes det

1. **Aftale** (`reception_agreements`): ejeren bekræfter abonnementet; hver bekræftelse er en ny version, der gemmer
   prisen. Betaling pr. henvendelse kan ikke længere vælges (`422 plan_discontinued`).
2. **Kampagneopkald:** når Vapi har accepteret et udgående opkald, skrives en række i `campaign_calls` med
   opkaldsprisen (`net_minor`, 4 kr.). Når opkaldsrapporten kommer, sættes `connected_seconds` og
   `minutes_net_minor` = påbegyndte minutter × kampagnens `minute_net_minor` (2 kr.); et ubesvaret opkald har 0
   minutter. En kontakt ringes højst 2 gange og taler højst 180 sekunder; det begrænser prisen. Før start vises den
   højeste pris (kontakter × forsøg × (4 kr. + 3 min × 2 kr.) = 10 kr. pr. forsøg), og ejeren skal acceptere den.
3. **Indgående minutter:** `statement.inbound_minutes()` tæller påbegyndte minutter pr. opkald for alle `calls` i
   måneden, der hverken er kampagne- eller demo-opkald. Linjen `inbound_minutes` viser forbrug, de 300 inkluderede og
   eventuelle ekstra minutter à 1,50 kr. (0 kr., når forbruget er under 300). Måneder uden indgående opkald har ingen
   linje.
4. **Månedsoversigt** (`billing/statement.py`): abonnementslinjen + én linje pr. kampagne ("N udgående opkald, M
   samtaleminutter") + indgående minutter. Fakturaen (Stripe) bygges af den samme oversigt.
5. **Ambassadør-rabat** (50 % første måned) og bonusser regnes af fakturaens beløb og følger dermed den nye pris.

## Ældre data (rørt ikke ved)

- Ældre model-B-aftaler beholder deres gebyr-snapshot, og godkendte henvendelser fra dengang står stadig på de
  måneder, de blev godkendt. Der kan ikke oprettes nye.
- Kampagnekontakter, der blev afregnet som pakke (9 kr.), står stadig på deres måned (`campaign_contacts.charged_*`).
- Migrationen `campaign calls priced per call` flytter alle eksisterende kampagner til 4 kr. pr. opkald fra nu af.
- Migrationen `campaign calls priced per call plus started minute` (30. oktober) giver alle kampagner minutprisen
  2 kr. fra nu af; opkald rapporteret før da har `minutes_net_minor = 0`.
- Eksisterende abonnementer på 1.495 kr. ændres **ikke** automatisk. Prisen i en aftale er en snapshot, og en
  prisstigning over for eksisterende kunder kræver varsel (se vilkårene, afsnit 2: mindst 30 dage). Bekræfter en kunde
  abonnementet igen, får den nye version 2.495 kr.
