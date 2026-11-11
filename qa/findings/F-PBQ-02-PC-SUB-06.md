---
id: F-PBQ-02-PC-SUB-06
scenario: PC-SUB-06
reported_by: billing-qa
severity: S2
status: closed
owner_fix: fix-engineer
related: [F-PBQ-06-PC-ENT-02, F-PQ-03-X09]
---

## Kort
Én prøveperiode pr. KONTO, ikke pr. person eller kort. En ny e-mail (fx `navn+2@…`) med samme kort får en ny 14-dages prøve. Der findes ingen kort-fingerprint-kontrol.

## Trin til at genskabe
1. Konto A → checkout → trial (kort 4242).
2. Konto B (alias-e-mail, samme person) → `POST /privat/subscription/checkout` → `subscription_data.trial_period_days = 14`.

## Forventet
Uafklaret. Scenariet beder eksplicit om needs-decision.

## Faktisk
`trial_available(row)` (subscriptions.py:93-95) ser kun på rækken: `trial_ends_at is None and stripe_subscription_id is None`. Kortet er ikke kendt, før Stripe har det, og Dialogbot læser aldrig `payment_method.card.fingerprint`.

## Konsekvens
Kombineret med F-PBQ-06 (plan-apps forbliver efter trial) giver hver ny e-mail en ny konto med Plus-apps for evigt plus 3 velkomstcredits. Kombineret med F-PQ-03 og henvisninger giver hver alt-konto +3 credits til hovedkontoen (målt: 3 alt-konti → +9 credits, uden nogen plan).

## Beslutning nødvendig (Fürster)
A. Acceptér (de fleste B2C-tjenester gør det; kortet trækkes efter 14 dage, hvis man ikke opsiger).
B. Fingerprint-kontrol: ved `checkout.session.completed` hentes `payment_method.card.fingerprint`. Har det haft en trial før, sættes trialen til at slutte nu (`POST /subscriptions/<id> trial_end=now`), så der trækkes straks. Kræver en lille tabel over fingerprints.

## Evidens
- tests/qa/test_qa_pd_billing.py::test_pc_sub_06_new_email_same_card_is_refused_a_second_trial (xfail strict)
- ::test_pc_inv_08_self_referral_farm_without_any_plan (xfail strict, «inviter farmed 9 credits from 3 free alt-accounts»)

## Rodårsag / Rettelse / Verifikation

## Rettelse (udfyldes af fix-engineer)
- Beslutning (Fürster 2026-11-10): ÉT KORT = ÉN PRØVEPERIODE, og henvisningsbonus gives først, når den henviste har betalt en første rigtig periode.
- Rettelse, kort: ny tabel private_trial_cards (Stripe card fingerprint som PK, workspace_id SET NULL, stripe_subscription_id, first_trial_at). Ny reversibel migration d7f2b9c4e1a8 (oven på c9e4a7d2b1f6), testet op/ned, og alembic check er ren. Ingen kortdata gemmes. I upsert_from_stripe_subscription gælder: når et NYT abonnement kommer i trialing, hentes fingeraftrykket (default_payment_method → GET /payment_methods/{id}). Har kortet allerede givet en prøveperiode til en anden konto, afsluttes prøveperioden med det samme (POST /subscriptions/{id} trial_end=now, idempotency-key), og brugeren får besked («Kortet har allerede haft en prøveperiode …»). Ellers huskes kortet. Kan fingeraftrykket ikke hentes, står prøveperioden ved magt (fail-open, logges). Checkout-siden siger det på forhånd via custom_text.submit («Én prøveperiode pr. kort …», da/en). Rækken bevares ved kontosletning, så sletning og ny tilmelding ikke giver en ny prøveperiode.
- Rettelse, henvisning (lukker også F-PQ-03): referrals.try_activate belønner først, når paid_once er opfyldt (Stripe-abonnementet er active/past_due, eller opsagt med betalt periode efter prøveperioden). Den forsøges igen, når abonnementet bliver active. Operatørens growth-«activated» betyder derfor nu «har betalt».
- Tests: test_privat_subscription::test_one_trial_per_card (ny). test_privat_sharing::test_referral_once/needs_activation/monthly_cap/growth_operator_only er tilpasset (belønning kræver betalt periode).
- Filer: app/models/privat.py, app/models/__init__.py, alembic/versions/d7f2b9c4e1a8_private_trial_cards.py, app/modules/privat/subscriptions.py, app/modules/privat/referrals.py
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_one_trial_per_card (NB: den gamle xfail-test test_pc_sub_06 dokumenterer en forkastet løsning – checkout-payload – og står stadig som xfail)
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: samme testfil
- Dom: closed
