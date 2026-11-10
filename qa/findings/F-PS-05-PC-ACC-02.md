---
id: F-PS-05-PC-ACC-02
scenario: PC-ACC-02
reported_by: security-privacy
severity: S2
status: needs-decision
owner_fix: fix-engineer
related: [PC-ACC-03, PC-ACC-05]
---

## Kort
Privat har hverken «Slet min konto» eller «Eksportér mine data» (GDPR art. 15/17/20). Privatlivspolitikken lover rettighederne via «Skriv til …», så det er i dag en manuel proces uden værktøj, og der er ingen opbevaringsfrist på Privat-data.

## Trin til at genskabe
1. Route-listen (`all_routes`): ingen DELETE af konto/bruger og ingen eksport under /privat (heller ikke /auth/me).
2. web/src/components/privat/account.tsx: ingen slet/eksport-handling. Kun «Slet appens data» pr. app.

## Forventet
Scenariet: «slet konto og alle data (lister, grupper med andres numre, fødselsdage, kvitteringsfotos …); Stripe opsagt» og «eksportér mine data».

## Faktisk
- Intet endpoint/UI. Manuel sletning er teknisk mulig: en SAVEPOINT-test der sletter `workspaces`-rækken og `users`-rækken efterlader 0 rækker med brugerens id/workspace i nogen tabel (FK-cascade virker) – men filer i lageret (kvitteringsfotos, ønskebilleder, covers) slettes ikke af cascade, Stripe-abonnementet opsiges ikke, og der er intet operatørværktøj/runbook.
- Ingen retention-job for private_messages, private_calls (business_reply/summary), private_lookups dog prunes (2 dage).
- Opkald optages ikke (`artifactPlan: vapi.NO_RECORDING`), og AI-identitet oplyses i første replik – OK.
Alvorsgrad S2 (gap/needs-decision): rettighederne kan honoreres manuelt inden for 1 måned, men uden værktøj er risikoen for ufuldstændig sletning (filer, Stripe) høj. Scenariet foreslog S1 – qa-lead/Fürster beslutter.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_acc_02_03_no_account_deletion_and_no_export_in_privat (gap-register, grøn mens gap'et findes)
- Test: tests/qa/test_qa_pd_sec.py::test_ps_acc_02b_manual_erasure_leaves_personal_data_behind (grøn: DB-cascade er komplet)

## Beslutning ønskes
1. Selvbetjent «Slet konto» i Privat (opsig Stripe, slet filer, slet workspace+bruger) eller dokumenteret operatør-runbook/endpoint?
2. Eksport: JSON-download af lister, ønsker, grupper, aftaler, beskeder?
3. Opbevaringsfrist for chat/opkaldsresuméer (fx 24 mdr. inaktivitet)?

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Dom: closed | reopened
