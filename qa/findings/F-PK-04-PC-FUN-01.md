---
id: F-PK-04-PC-FUN-01
scenario: PC-FUN-01
reported_by: e2e-privat (PK)
severity: S1
status: fixed
owner_fix: fix-engineer (verify-email-side + e-mailtekst); ui-ux-engineer ved tekst/tema
related: [F-PQ-02-X07, F-E2A-05-A03]
---

## Kort
Privat-funnelen knækker ved e-mailbekræftelsen. «Prøv gratis i 14 dage» → «Opret privat konto» (orange) → /privat/konto?plan=plus, hvor der står «Bekræft din e-mail for at bruge Dialogbot Privat». E-mailen siger «… så kan du komme i gang med at sætte din AI-receptionist op», og linket åbner Erhvervs blå /verify-email: «Bekræftelsen beskytter arbejdsrummet og er nødvendig, før du kan oprette virksomheder» → «Fortsæt til arbejdsrum →» (/onboarding/workspace). Der er ingen vej tilbage til Privat-checkouten med den valgte plan.

## Trin til at genskabe
1. Anonym på mobil-390: /privat → «Prøv gratis i 14 dage».
2. Udfyld «Opret privat konto» → lander på /privat/konto?plan=plus&interval=month. Checkout kan ikke starte (`POST /privat/subscription/checkout` → 403 `email_not_verified`).
3. Åbn bekræftelsesmailen (simuleret postkasse) → /verify-email?token=…

## Forventet
Brief/regel: «"Prøv gratis i 14 dage" leads straight to checkout (name, address, phone, e-mail, card)». Privat skal være visuelt adskilt (orange) og ikke sende en privatperson ind i Erhvervs arbejdsrums-onboarding.

## Faktisk
- Mailteksten er Erhvervs: app/modules/integrations/email_texts.py:37 «sætte din AI-receptionist op».
- `/verify-email` (web/src/app/verify-email/page.tsx:19,28) kender kun `/ambassador`-fortsættelse (localStorage `db_after_verify`). Alle andre får «Fortsæt til arbejdsrum» → /onboarding/workspace.
- localStorage hjælper heller ikke, når mailen åbnes i Mail-appen på iPhone, for den åbner Safari med tom storage, og det er netop den 60-åriges sti.
- Brugeren kommer kun videre ved selv at finde tilbage til /privat/konto?plan=plus. Så starter checkouten (testen gør det manuelt).

## Forslag
Privat-signup sender `signup_intent: null`. Gem i stedet en server-side markør (fx `signup_intent="privat"` eller `next` i verify-tokenet), så (a) mailen bruger en Privat-tekst og et link til `/verify-email?next=/privat/konto?plan=…`, og (b) /verify-email i orange tema viser «Fortsæt til din prøveperiode» og starter checkouten. Alternativt kan man lade checkout ske før e-mailbekræftelse (Stripe bekræfter e-mailen alligevel). Det er en needs-decision.

## Evidens
- qa/evidence/PC-FUN-01/PK-mobil-390-{signup,efter-signup,efter-bekraeft,checkout}.png
- Test: web/e2e/qa/privat-deep/core/brand-funnel.spec.ts «PC-FUN-01» (består kun, fordi testen selv går tilbage til /privat/konto?plan=plus; annotation url-after-verify = /verify-email)

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Rodårsag: en Privat-signup sendte signup_intent null. Bekræftelsesmailen og /verify-email kendte kun Erhverv (og /ambassador via localStorage).
- Rettelse: Privat-signup sender signup_intent «privat» (identity.PRIVAT_INTENT; aldrig en product_intent – workspaces.service og /opsaetning/1 ignorerer den). issue_verification tilføjer &for=privat til linket og audience=privat til mailen. Mailen bruger verify_heading_privat/verify_body_privat (8 sprog i email_texts.py). /verify-email?for=privat vises i orange ramme og har knappen «Fortsæt til din prøveperiode» → /privat/konto?planer=1. Virker også når mailen åbnes i en anden browser.
- Filer: app/modules/identity/service.py, identity/router.py (doc), workspaces/service.py, integrations/email_texts.py, email_templates.py, app/worker/runner.py, web/src/app/signup/page.tsx, web/src/app/verify-email/page.tsx, web/src/app/opsaetning/1/page.tsx, web/src/i18n/messages/*/auth.json
- Test: web/e2e/qa/privat-deep/core/brand-funnel.spec.ts (kræver ny stak)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
