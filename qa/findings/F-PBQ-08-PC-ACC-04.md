---
id: F-PBQ-08-PC-ACC-04
scenario: PC-ACC-04
reported_by: billing-qa
severity: S2
status: fixed
owner_fix: fix-engineer
related: [PC-SUB-11, PC-SUB-13, PC-SUB-14]
---

## Kort
Privat sender ingen egne e-mails om abonnementet: ingen om start af prøve, ingen «prøven slutter om 3 dage, så trækker vi 99 kr.», ingen kvittering for første betaling, ingen dunning ved fejlet betaling (E06 findes kun for Erhverv), ingen bekræftelse ved opsigelse og ingen om refusion. Fakturaer og kvitteringer findes kun i Stripe Billing Portal («Administrér abonnement»). Konto har ingen fakturaliste og intet ord om, hvor kvitteringen er.

## Trin til at genskabe
Kør PC-SUB-11/13/14 (trial → active, opsigelse i trial, past_due → canceled). `email_deliveries`/outbox for kundens adresse er tom (bortset fra e-mail-verifikation). `invoice.payment_failed` for en Privat-faktura → `unmatched`.

## Forventet
Uafklaret for Privat. Prisreglerne kræver «failed payment → dunning e-mail (E06), refund → refund-confirmed e-mail». Forbrugere bør desuden varsles før første træk efter en gratis prøve. Det er god praksis og for abonnementer typisk et krav, men det er en juridisk vurdering for Fürster.

## Faktisk
Alt afhænger af Stripe Dashboard → Settings → Customer emails (kvitteringer, «trial ending reminder», «failed payment»). Indstillingerne kan ikke verificeres fra kode eller testmode i QA-stakken. Portal uden kunde → 501 `not_configured` med forklarende tekst (OK).

## Beslutning nødvendig (Fürster)
A. Stripe sender alt: slå kvitteringer, trial-reminder (7 dage før), failed-payment og refund-mails til i Stripe (live og test), og skriv i Konto «Kvitteringer finder du under Administrér abonnement».
B. Dialogbot sender egne Privat-mails (E06-variant) og lytter på `customer.subscription.trial_will_end`, `invoice.payment_failed`, `invoice.paid` og `charge.refunded`.

## Evidens
- tests/qa/test_qa_pd_billing.py::test_pc_acc_04_invoices_only_through_the_stripe_portal, ::test_pc_sub_11_…, ::test_pc_sub_14_… (asserter at der IKKE sendes egne mails = status quo)

## Rodårsag / Rettelse / Verifikation

## Rettelse (udfyldes af fix-engineer)
- Beslutning (Fürster 2026-11-10): Dialogbot sender sine EGNE abonnementsmails, også for Privat.
- Hvad var der i forvejen: Erhverv sendte ingen mails om betaling. Stripe sender selv Erhvervs fakturaer, men der var ingen dunning (E06) og ingen refusionsbekræftelse (billing-qa bølge 1). Privat sendte ingen abonnementsmails overhovedet.
- Rettelse: nyt modul app/modules/billing/customer_mails.py (receipt, payment_failed, refund, trial_ending) i det brandede layout (Email.audience: Privat = #C4461A og «Dialogbot Privat», Erhverv = blå). Tekster på 8 sprog i email_texts.py. Køres som email.branded med dedupe pr. Stripe-objekt, så et genafspillet webhook aldrig sender to gange.
  - Privat (subscriptions.on_billing_event, matchet på Privat-kundens Stripe-customer): invoice.paid > 0 → kvittering, invoice.payment_failed → dunning, charge.refunded → refusion bekræftet. customer.subscription.trial_will_end (3 dage før) → «Din prøveperiode slutter om 3 dage» med beløb og dato; sendes ikke, hvis prøveperioden er opsagt.
  - Erhverv (billing/stripe.py _owner_mail til arbejdsrummets ejere): invoice.payment_failed → dunning, charge.refunded/credit_note → refusion bekræftet. Kvittering for betalt Erhverv-faktura sender Stripe fortsat selv (hosted invoice).
- Ikke dækket: refusion af kreditpakker (Checkout uden Stripe-customer kan ikke matches; se credit_pack_refund-fundet).
- Tests: test_privat_subscription::test_privat_sends_its_own_billing_mails, test_stripe_billing::test_erhverv_dunning_and_refund_mails_to_the_owner (nye; simuleret mail via outbox)
- Filer: app/modules/billing/customer_mails.py (ny), app/modules/billing/stripe.py, app/modules/privat/subscriptions.py, app/modules/integrations/email_templates.py, app/modules/integrations/email_texts.py
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)
