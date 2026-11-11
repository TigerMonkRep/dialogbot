---
id: F-PS-05-PC-ACC-02
scenario: PC-ACC-02
reported_by: security-privacy
severity: S2
status: closed
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

## Rodårsag (udfyldes af fix-engineer)
Der var hverken bygget eksport eller sletning. Fürster besluttede 2026-11-10 21:59 (B): selvbetjent eksport og sletning under Konto → «Dine data».

## Rettelse (udfyldes af fix-engineer #3)
- `gdpr.py` + `household_router.py`. Model `PrivateDataExport` + migration `c9e4a7d2b1f6`.
- **Eksport:** `POST /privat/data-export` (202, maks. 3 pr. døgn, idempotent mens den laves) → worker-event `privat.data_export` → zip med `data.json` + `oversigt.txt` (læsbar oversigt, da/en). Indhold: konto, profil, plan, husstand, apps + appdata, egne opgaver/lister/ønskelister med punkter og historik, delt-med-mig (kun egne punkter/reservationer), fællesgave-tilsagn, beskeder, opkaldslog med virksomhedens svar, aftaler, fødselsdage, regninger, credits, bookinger, sendte invitationer, henvisninger, grupper, enheder og funnel-svar. Aldrig: hvem der har reserveret ejerens ønsker, andres data, tokens, kodehashes eller vapi-id'er. Linket sendes på e-mail, kræver samme login og udløber efter 7 dage. Derefter slettes indholdet (lazy + worker-sweep).
- **Slet konto:** `POST /privat/account/delete {confirm_email}`. Stripe-abonnementet opsiges først. Fejler Stripe, slettes intet (502). Husstand: ejerens medlemmer mister Familie, og et medlem forlader husstanden. Workspace + alt i den (CASCADE) og filer under ws-præfikset slettes. Reservationer og tilsagn på andres lister frigives, og personens navn fjernes fra deres punkter. Grupper, invitationer, henvisninger, push, eksporter, ventende e-mails/SMS-koder, funnel-kladder og idempotency-nøgler slettes, og Stripe-webhook-payloads, der nævner personen, skrubbes. Sessioner afsluttes, og login slettes, *medmindre* login også bruges uden for Privat (erhvervs-workspace, ambassadør, operatør) → `login_kept`. Audit-rækken `privat.account_deleted` har kun tællere og flag, ingen PII.
- Juridisk: legal.json lover retten til sletning/dataportabilitet for Privat, men ingen frist → sletning sker straks. 30 dage gælder kun erhvervskunder ved opsigelse. Fakturaer forbliver hos Stripe (bogføringsloven, 5 år, «Betaling»-afsnittet). Private opkald optages aldrig.
- Web: `components/privat/account-data.tsx` («Dine data» på Konto: eksport, download via `?eksport=`-link, slet med genindtastet e-mail, danger-knap), i18n `myData.*` ×8.
- Test: `tests/test_privat_gdpr.py` (5/5 grønne: eksport komplet og kun egne data, linket udløber + rate limit, sletning (intet kan hentes, login fejler, andre urørt, reservation frigivet, Familie væk, fil slettet, audit uden PII), Stripe-fejl sletter intet, login bevares ved erhvervsbrug).
- Gap-register-testen `tests/qa/test_qa_pd_sec.py::test_ps_acc_02_03_no_account_deletion_and_no_export_in_privat` fejler nu som forventet (endpoints findes). security-privacy/verifier skal vende den.
- Ikke bygget: opbevaringsfrist for chat/opkaldsresuméer (beslutning 3) – stadig needs-decision.
- Commit: ingen (qa-lead committer).

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_privat_gdpr.py, test_ps_acc_02_03
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: samme testfil
- Dom: closed
