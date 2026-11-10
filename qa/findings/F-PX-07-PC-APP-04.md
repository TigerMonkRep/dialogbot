---
id: F-PX-07-PC-APP-04
scenario: PC-APP-04
reported_by: voice-qa (PX)
severity: S3
status: new
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
