# Priser – ét tilbud

Gældende fra 28. oktober 2026. Alle priser er ekskl. moms (25 % lægges på fakturaen).

| | Pris |
|---|---|
| **Abonnement** | **Fra 2.495 kr./md.** – telefon, chat, booking, opsummering af hver henvendelse. Ingen pris pr. henvendelse. |
| **Udgående kampagneopkald** | **4 kr. pr. udgående opkald** – hvert opkald, der ringes, tæller, også et nyt forsøg. |
| Opsætning | Gratis, cirka en halv time. |
| Binding | Ingen. Opsigelse til udgangen af måneden. |

Tidligere fandtes to modeller (1.495 kr./md. eller 149 kr. pr. godkendt henvendelse) og kampagnepakker à 9 kr. pr.
kontakt. De findes ikke mere.

## Hvor tallene bor

- **Kode:** `app/modules/billing/prices.py` – `SUBSCRIPTION_MONTHLY_NET_MINOR` (249.500 øre) og
  `CAMPAIGN_CALL_NET_MINOR` (400 øre). Prisaftalen, kampagner, Peters salgsmanuskript og testene læser dem derfra.
- **Tekster** (skal rettes i hånden, når prisen ændres): `web/src/app/priser`, `byggevejledning`, forsiden
  (`(public)/page.tsx`, inkl. strukturerede data), `ai-receptionist`, `chatbot`, `ai-telefonsvarer`, `vilkaar`,
  `proev-chat.tsx`, `web/public/llms.txt`, `web/public/materiale/*.html`, `app/modules/social/topics.py`
  (`FACTS`, `ALLOWED_AMOUNTS`) og `design-reference/byggevejledning`.
- `tests/test_prices.py` fejler, hvis en gammel pris eller "model A/B" dukker op igen i disse tekster.

## Sådan afregnes det

1. **Aftale** (`reception_agreements`): ejeren bekræfter abonnementet; hver bekræftelse er en ny version, der gemmer
   prisen. Betaling pr. henvendelse kan ikke længere vælges (`422 plan_discontinued`).
2. **Kampagneopkald:** når Vapi har accepteret et udgående opkald, skrives en række i `campaign_calls` med prisen på
   det tidspunkt. En kontakt ringes højst 2 gange og taler højst 180 sekunder; det begrænser prisen. Før start vises
   den højeste pris (kontakter × forsøg × 4 kr.), og ejeren skal acceptere den.
3. **Månedsoversigt** (`billing/statement.py`): abonnementslinjen + én linje pr. kampagne ("N udgående opkald").
   Fakturaen (Stripe) bygges af den samme oversigt.
4. **Ambassadør-rabat** (50 % første måned) og bonusser regnes af fakturaens beløb og følger dermed den nye pris.

## Ældre data (rørt ikke ved)

- Ældre model-B-aftaler beholder deres gebyr-snapshot, og godkendte henvendelser fra dengang står stadig på de
  måneder, de blev godkendt. Der kan ikke oprettes nye.
- Kampagnekontakter, der blev afregnet som pakke (9 kr.), står stadig på deres måned (`campaign_contacts.charged_*`).
- Migrationen `campaign calls priced per call` flytter alle eksisterende kampagner til 4 kr. pr. opkald fra nu af.
- Eksisterende abonnementer på 1.495 kr. ændres **ikke** automatisk. Prisen i en aftale er en snapshot, og en
  prisstigning over for eksisterende kunder kræver varsel (se vilkårene, afsnit 2: mindst 30 dage). Bekræfter en kunde
  abonnementet igen, får den nye version 2.495 kr.
