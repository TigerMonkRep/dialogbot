---
id: F-PBQ-05-PC-SUB-21
scenario: PC-SUB-21
reported_by: billing-qa
severity: S2
status: confirmed
owner_fix: fix-engineer
related: [F-PBQ-03-PC-SUB-21]
---

## Kort
En refunderet kreditpakke (`charge.refunded`, fuld refusion af 29 kr.) ændrer intet i ledgeren. Kunden beholder 10 credits (op til 3 ekstra opkald), og Dialogbot har tilbagebetalt pengene.

## Trin til at genskabe
1. Køb pakke → `checkout.session.completed` (paid, 2900, payment_intent pi_x) → ledger `purchase +10`.
2. Operatøren refunderer i Stripe → `charge.refunded` med `payment_intent=pi_x`, `amount_refunded=2900`.

## Forventet
Ledger `refund -10` (eller så mange, der er tilbage, uden negativ saldo), med source_ref `stripe-refund:<charge>`, idempotent ved replay. Er credits allerede brugt, så noteres det til operatøren.

## Faktisk
`process_event` sender `charge.refunded` til Erhverv-fakturastien (`_refunded_invoice_id` → `/invoice_payments`) og svarer `unmatched`/`ignored`. Saldo efter fuld refusion: 13 (3 velkomst + 10).

## Evidens
- tests/qa/test_qa_pd_billing.py::test_credit_pack_refund_takes_the_credits_back (fejler: «after a full refund the balance is 13»)

## Note
Kræver, at refusionen kan kobles til sessionen: `payment_intent_data.metadata` sættes allerede (payments.py:51), så `charge.metadata` har `kind=privat_credits` og `workspace_id`.

## Rodårsag / Rettelse / Verifikation
