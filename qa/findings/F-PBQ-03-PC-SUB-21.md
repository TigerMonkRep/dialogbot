---
id: F-PBQ-03-PC-SUB-21
scenario: PC-SUB-21
reported_by: billing-qa
severity: S0
status: closed
owner_fix: fix-engineer
related: [F-PBQ-05-PC-SUB-21]
---

## Kort
Kreditpakkens Checkout viser Stripes rabatkodefelt (`allow_promotion_codes: true`, payments.py:50). Betaler kunden med en gyldig Privat-kode, ignorerer webhooken betalingen, fordi `amount_total < PRIVAT_CREDIT_PACK[cur]` (payments.py:78). Kunden har betalt, men får 0 credits.

## Trin til at genskabe
1. En Privat-rabatkode findes, fx 50 % (discounts.create → `_mirror_to_stripe`). Kuponen oprettes UDEN `applies_to` (discounts.py:90-101) og gælder derfor alle produkter, også kreditpakken.
2. `POST /privat/credits/checkout` → payload har `allow_promotion_codes: true`.
3. Kunden taster koden på Stripe-siden og betaler 14,50 kr. → `checkout.session.completed` med `payment_status=paid`, `amount_total=1450`.

## Forventet
Prisregel: 10 credits = 29 kr. inkl. moms (2.320 + 580 øre). Enten kan der ikke gives rabat på pakken (intet kodefelt), eller også bliver en betalt session altid til +10 credits.

## Faktisk
Webhooken svarer `outcome: ignored`. Ledger: kun velkomst-`grant 3`, ingen `purchase`. Pengene er trukket, og der er ingen refusion og ingen alarm.

## Evidens
- Test: tests/qa/test_qa_pd_billing.py::test_pc_sub_21_paid_with_a_promotion_code_still_grants_the_credits (fejler: `paid 14,50 kr., outcome=ignored, credits=0`)

## Forslag
Fjern `allow_promotion_codes` fra kreditpakkens payload (anbefalet, fordi en abonnementskode ikke bør give rabat på credits). Hvis rabat på credits er ønsket, så tildel credits ved `payment_status=paid`, når `total_details.amount_discount` forklarer forskellen. Det sidste er en prisbeslutning for Fürster.

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Rettelse (konservativ – ingen kunde kan betale for lidt): allow_promotion_codes er fjernet fra kreditpakkens Checkout. En betalt session under prisen giver stadig ingen credits, men logges som error privat.credit_pack_underpaid, så en person refunderer eller giver credits manuelt.
- needs-decision (Fürster): skal rabatkoder kunne give billigere credits? I så fald skal kuponer have applies_to, og webhooken skal acceptere amount_discount.
- billing-qa tilpasser test_pc_sub_21 til den valgte vej.
- Filer: app/modules/privat/payments.py
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_pc_sub_21_no_promotion_codes_on_the_topup, topup_once_per_session
- Fejler testen uden rettelsen? ja – f2b3d11 payments.py:50 har allow_promotion_codes=True (testen 404 på baseline pga. omdøbt endpoint)
- Naboscenarier kørt: test_privat_call_balance.py, test_qa_pd_billing.py
- Dom: closed
