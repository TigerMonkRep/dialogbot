---
id: F-PBQ-01-PC-SUB-07
scenario: PC-SUB-07
reported_by: billing-qa
severity: S0
status: fixed
owner_fix: fix-engineer
related: []
---

## Kort
To Checkout-sessioner, der åbnes før nogen af dem er gennemført, giver to Stripe-abonnementer på samme kort. Begge har 14 dages prøve og trækker bagefter hver deres beløb. Vagten `subscription_exists` (subscriptions.py:220-223, tilføjet 21:12) fanger kun et abonnement, som allerede er spejlet ind i rækken.

## Trin til at genskabe
1. Konto uden abonnement (status none).
2. `POST /privat/subscription/checkout {"plan":"basis"}` → 200 (fane 1).
3. `POST /privat/subscription/checkout {"plan":"plus"}` → 200 (fane 2, PlanSheet i Butikken, tilbage-knap eller e-mail-link). Begge payloads har `subscription_data.trial_period_days=14`.
4. Gennemfør begge med 4242 → `checkout.session.completed` x 2 → begge "applied".
5. Kunden opsiger det abonnement, kontoen viser (det sidste) i portalen.

## Forventet
Én Privat-konto har højst ét kørende Stripe-abonnement (PC-SUB-07). Prisreglen: Basis 49 kr./md. eller Plus 99 kr./md., ikke begge.

## Faktisk
- Fake Stripe har 2 live abonnementer: `sub_cs_test_pbq_1` (basis, trialing) og `sub_cs_test_pbq_2` (plus, trialing). Efter prøveperioden: 4.900 + 9.900 = **14.800 øre/md.**
- `private_subscriptions.stripe_subscription_id` = kun det sidste (`..._2`). Det første er usynligt i Dialogbot.
- Når kunden opsiger `..._2`, bliver `..._1` (Basis) ved med at trække. Kontoen viser «Opsagt», og der er ingen rettigheder, når perioden er slut.
- `upsert_from_stripe_subscription` (subscriptions.py ~linje 360) overskriver blot `stripe_subscription_id` med det nye id. Ingen alarm, ingen annullering af det gamle.

## Evidens
- Test: tests/qa/test_qa_pd_billing.py::test_pc_sub_07b_two_open_checkouts_completed_leave_two_billing_subscriptions (fejler i dag)
- Regression for den sekventielle sti (grøn efter 21:12-vagten): ::test_pc_sub_07_active_customer_cannot_start_a_second_subscription

## Forslag (ikke bindende)
- I `on_checkout_completed`/`upsert_from_stripe_subscription`: hvis rækken allerede har et andet LIVE abonnement (trial/active/past_due) end det nye sid, så annullér det nye i Stripe (`DELETE /subscriptions/<ny>`, prøve = intet trukket) eller det gamle med proration, og log det. Behold præcis ét.
- Og/eller i `checkout()`: genbrug/expire en åben session for samme workspace (`POST /checkout/sessions/<id>/expire`) før en ny oprettes.
- UI (ui-ux): «Skift plan» i Konto og PlanSheet for en kunde med plan skal gå til portalen, nu hvor API'et svarer 409 `subscription_exists`.

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Rodårsag: upsert overskrev stripe_subscription_id med det nyeste abonnement uden at håndtere det andet.
- Rettelse: når en konto, der allerede har et entitled abonnement, får et andet live abonnement, annulleres det nye hos Stripe (DELETE /subscriptions/{id}) og logges (privat.duplicate_subscription_canceled / _not_canceled). Rækken beholder det første. outcome = dup_canceled (≤ 16 tegn til webhook_events.outcome).
- Filer: app/modules/privat/subscriptions.py
- Test: tests/qa/test_qa_pd_billing.py::test_pc_sub_07b (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
