---
id: F-PX-07-PC-APP-04
scenario: PC-APP-04
reported_by: voice-qa (PX)
severity: S3
status: closed
owner_fix: fix-engineer
related: [F-PX-02-PC-APP-04]
---

## Kort
Standard-«Du må spørge om» bliver ugrammatisk, når formålet er i bydeform: «Om de kan aflever cyklen torsdag efter kl. 15, og hvad det koster» (vises på opgavekortet under «Formål» og står i opkaldsmanuset).

## Trin
1. «Ring til cykelværkstedet og find en tid torsdag efter klokken tre» → vælg Cykelmageren.
2. /privat/opgaver/<id>: Formål = «Om de kan aflever cyklen …». Samme kort viser Tidspunkt «–», selvom titlen siger «torsdag efter kl. 15».

## Forventet
Naturligt dansk (voice-qa: «Danish number reading, times …», brand: kort og klart).

## Faktisk
`calls.propose`: `may_ask = f"Om de kan {rules.lower_first(purpose)} …"` – formål «Aflever cyklen» giver «kan aflever».

## Evidens
- pd-results/PX/out-rerun/…voice-cal…/test-failed-1.png (første kørsel, kort vist), web/e2e/qa/privat-deep/x/voice-calls.spec.ts

## Forslag
«Om de kan hjælpe med: aflever cyklen …» eller lad modellen levere may_ask; vis vinduet under Tidspunkt.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: standard-may_ask lyder nu «Om de kan hjælpe med: <formål>[ <tidsrum>], og hvad det koster». Det er grammatisk uanset formålets form, og tidsrummet gentages ikke, hvis det allerede står i formålet.
- Ikke ændret: «Tidspunkt –» på kortet (det er ui-ux/tasks.tsx).
- Filer: app/modules/privat/calls.py
- Test: tests/test_privat.py::test_default_may_ask_reads_right_whatever_the_purpose (rød før: «Om de kan aflever cyklen … torsdag efter kl. 15 torsdag efter kl. 15»; grøn efter)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_default_may_ask_reads_right_whatever_the_purpose
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: samme testfil
- Dom: closed
