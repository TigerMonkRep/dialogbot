---
id: F-PBQ-09-PC-SUB-07
scenario: PC-SUB-07
reported_by: billing-qa
severity: S0
status: closed
owner_fix: fix-engineer
related: [F-PBQ-01-PC-SUB-07]
---

## Kort
Rest efter rettelsen af F-PBQ-01 (`_cancel_duplicate`, subscriptions.py ~364-422). Den dublerede abonnement annulleres med `DELETE /subscriptions/<id>`, men refunderes ikke. Uden prøveperiode (en tilbagevendende kunde, hvor trial er brugt) er den dubleredes første faktura allerede BETALT. Kunden mister den.

## Trin til at genskabe
1. Konto med tidligere abonnement, der er slut (`entitled=false`, trial brugt).
2. To checkouts før nogen er gennemført: Basis og Plus. Ingen `trial_period_days`, og begge trækkes med det samme (49 + 99 kr.).
3. Begge `checkout.session.completed` → `applied` og `dup_canceled`.

## Forventet
Kunden betaler for præcis ét abonnement. Den dublerede betaling refunderes (`POST /refunds` for `latest_invoice`'s betaling eller en kreditnota), og det logges.

## Faktisk
Fake Stripe: 1 live abonnement (korrekt), men ingen `/refunds`- eller `/credit_notes`-kald. Betalt 14.800 øre for to første perioder, beholdt **9.900 øre** uden ydelse. Rækken beholder det FØRSTE (Basis), så den plan kunden valgte sidst (Plus), bliver annulleret uden besked i UI.

## Evidens
- Test: tests/qa/test_qa_pd_billing.py::test_pc_sub_07c_paid_duplicate_without_trial_is_refunded (fejler)

## Forslag
I `_cancel_duplicate`: hvis abonnementet ikke er `trialing`, så hent `latest_invoice` → refundér betalingen (`POST /refunds {payment_intent}` eller `/credit_notes` med `refund_amount`), med idempotency-key pr. subscription id. Overvej desuden at forhindre det i `checkout()`: expire en åben session for samme workspace før en ny oprettes.

## Rodårsag / Rettelse / Verifikation

## Rettelse (udfyldes af fix-engineer)
- Rettelse: _cancel_duplicate refunderer, når status ikke er trialing og latest_invoice er paid med amount_paid > 0: POST /refunds {payment_intent} med idempotency-key privat-dup-refund-<sid>. Fejl logges som error (privat.duplicate_subscription_not_refunded), så en person kan rydde op.
- Filer: app/modules/privat/subscriptions.py
- Test: tests/qa/test_qa_pd_billing.py::test_pc_sub_07c (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_pc_sub_07c_paid_duplicate_without_trial_is_refunded
- Fejler testen uden rettelsen? ja – på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent): ['applied','applied'] uden refusion
- Naboscenarier kørt: test_qa_pd_billing.py
- Dom: closed
