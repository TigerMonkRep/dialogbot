---
id: F-PBQ-02-PC-SUB-06
scenario: PC-SUB-06
reported_by: billing-qa
severity: S2
status: needs-decision
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
