---
id: F-VF-07-PX-CALL-03
scenario: PC-CALL-03
reported_by: verifier
severity: S3
status: new
owner_fix: fix-engineer / ui-ux-engineer
related: [F-PX-08-PC-CALL-03]
---

## Kort
Parallelle «Godkend» med samme Idempotency-Key giver 409 til det andet kald, mens det første kører (e2e x/voice-calls.spec.ts PC-CALL-01/02/03: 2 af 6 kørsler, «svar 200,200,200,409» / «200,200,409,200»). Der ringes kun ét opkald, og der er ingen 500. Spørgsmålet er, om UI'et viser 409 som en fejl på et opkald, der faktisk er i gang (det oprindelige brugerproblem i F-PX-08). e2e-testen forventer 4×200 og er derfor flaky.
