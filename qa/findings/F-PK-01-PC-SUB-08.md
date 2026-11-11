---
id: F-PK-01-PC-SUB-08
scenario: PC-SUB-08
reported_by: e2e-privat (PK)
severity: S0
status: closed
owner_fix: fix-engineer
related: [PC-SUB-07, F-BQ-002-X08]
---

## Kort
To Checkout-sessioner startet før den første er gennemført (dobbelttryk på «Start prøveperiode», to faner, tilbage-knap og prøv igen) kan begge betales. Resultatet er to Stripe-abonnementer på samme konto. Databasen husker kun det sidste, så det første bliver forældreløst: det trækker penge efter prøveperioden og kan ikke opsiges i appen.

## Trin til at genskabe
1. Ny konto uden plan. Send `POST /api/v1/privat/subscription/checkout {"plan":"plus","interval":"month"}` to gange parallelt. Begge giver 200 med hver sin session-URL.
2. Betal begge sessioner i den falske Stripe med 4242 4242 4242 4242. Begge giver 303 til `success_url`.
3. `GET /__qa/stripe/sessions`: to sessioner `complete`, hver med sit eget `sub_qa_…` og `trial_period_days=14`.
4. `private_subscriptions.stripe_subscription_id` = kun det andet abonnement.

## Forventet
PC-SUB-08: «Højst én Checkout-session pr. klik-serie, eller to sessioner hvor kun én kan gennemføres; aldrig to abonnementer». Én prøveperiode pr. konto (`trial_available`).

## Faktisk
Se qa/evidence/PC-SUB-08/PK-api-probe.txt: `[200, 200]` → begge `complete` (`sub_qa_b0a9d4e2ee1e`, `sub_qa_0e6e38f58237`). Rækken peger kun på `sub_qa_0e6e…`. Den nye SUB-07-vagt (`subscriptions.py:219`, `row.stripe_subscription_id and …`) hjælper ikke her: den slår først til, når en session er gennemført, og de åbne sessioner er allerede udstedt. I web er `PlanSheet.go` beskyttet med `busy`, men knappen findes ikke kun ét sted (Konto og paywall), og to faner eller tilbage og frem omgår den.

## Forslag (til fix-engineer)
- Ved checkout: genbrug eller udløb (`POST /checkout/sessions/{id}/expire`) en åben session for samme workspace i stedet for at oprette en ny. Alternativt brug Stripe-idempotency-key pr. workspace+plan+interval i et kort vindue.
- Webhook: hvis `checkout.session.completed` kommer for et workspace, der allerede har et andet kørende abonnement, så annullér det nye straks i Stripe (eller marker det til refusion) og log det.

## Evidens
- qa/evidence/PC-SUB-08/PK-api-probe.txt
- Test: tests/qa/test_qa_pd_core.py::test_sub08_parallel_checkout_never_two_subscriptions

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Rettet sammen med F-PBQ-01/F-PBQ-09: webhooken (upsert_from_stripe_subscription) annullerer et nyt live abonnement på en konto, der allerede har et aktivt (outcome dup_canceled), og refunderer den betalte første faktura, hvis der ingen trial er. Sekventielt: 409 subscription_exists (F-PFX-02).
- Filer: app/modules/privat/subscriptions.py
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: live :8400: tests/qa/test_qa_pd_core.py::test_sub08 3/3 grøn. NB: første kørsel rød fordi fake Stripe ikke simulerede DELETE /subscriptions (log privat.duplicate_subscription_not_canceled) – harness rettet, og testen tjekker nu levende abonnementer, ikke kun gennemførte sessioner
- Fejler testen uden rettelsen? indirekte – samme rettelse som F-PBQ-01 (test_pc_sub_07b fejler på f2b3d11)
- Naboscenarier kørt: test_qa_pd_core.py (16), test_qa_pd_billing.py
- Dom: closed
