---
id: F-PBQ-04-PC-SUB-13
scenario: PC-SUB-13
reported_by: billing-qa
severity: S2
status: confirmed
owner_fix: ui-ux-engineer
related: []
---

## Kort
Opsiger man i prøveperioden (Stripe `cancel_at_period_end=true`, status stadig `trialing`), siger Konto stadig «N dage tilbage af prøveperioden · Derefter Plus til 99 kr./md.». Kunden får at vide, at der trækkes, selv om intet trækkes. Den rigtige linje «Opsagt – slutter <dato>» vises kun for `status === "active"`.

## Trin til at genskabe
1. Trial via checkout → i portalen: «Opsig» (cancel at period end).
2. `customer.subscription.updated` med `status=trialing`, `cancel_at_period_end=true` → API: `status=trial`, `cancel_at_period_end=true`, `entitled=true` (korrekt).
3. /privat/konto.

## Forventet
Scenariet siger: Konto viser «Opsagt – adgang til <dato>».

## Faktisk
account.tsx (linjen `p.status === "trial" && <p …>`) tjekker ikke `cancelAtPeriodEnd` og viser `plan.trialThen` («Derefter {plan} til {price}/md.»). `plan.cancelAtEnd` vises kun under `p.status === "active"`.

Backend er korrekt: adgangen varer til trial_end, derefter `entitled=false`, og der laves ingen faktura (test_pc_sub_13_cancel_in_trial_keeps_rights_to_trial_end_then_nothing er grøn).

## Evidens
- tests/qa/test_qa_pd_billing.py::test_pc_sub_13_ui_trial_canceled_does_not_promise_the_charge (statisk check af account.tsx, fejler)

## Forslag
I trial-linjen: når `p.cancelAtPeriodEnd` er sat, vis `plan.cancelAtEnd` med `trial_ends_at` i stedet for `trialThen`. Filen ejes af ui-ux-engineer i fase 2.

## Rodårsag / Rettelse / Verifikation
