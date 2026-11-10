---
id: F-PFX-02-PC-SUB-07
scenario: PC-SUB-07
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S0
status: fixed
owner_fix: fix-engineer
related: []
---

## Kort
En kunde med et kørende abonnement kunne starte endnu en Checkout og få to Stripe-abonnementer.

## Rettelse (udfyldes af fix-engineer)
- Rodårsag: subscriptions.checkout() blokerede ikke, når der allerede kørte et abonnement.
- Rettelse: checkout() svarer 409 `subscription_exists` (extra portal=true), når rækken har et stripe_subscription_id, der stadig giver rettigheder (trial, active, past_due eller opsagt men betalt til periodens slut). Web (lib/privat/api.ts subscriptionCheckout) sender så kunden til Billing Portal. Kapløbet mellem to åbne Checkouts er rettet i F-PBQ-01/F-PBQ-09.
- Tests tilpasset til reglen: test_discount_codes, test_privat_subscription::test_checkout_completed_and_session_sync, test_privat_branding, test_qa_privat_x07 (anden checkout giver nu 409).
- Filer: app/modules/privat/subscriptions.py, web/src/lib/privat/api.ts
- Test: tests/test_privat_subscription.py::test_no_second_checkout_while_a_subscription_runs
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
