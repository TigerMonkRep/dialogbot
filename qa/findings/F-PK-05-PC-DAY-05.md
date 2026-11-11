---
id: F-PK-05-PC-DAY-05
scenario: PC-DAY-05
reported_by: e2e-privat (PK)
severity: S2
status: new
owner_fix: ui-ux-engineer (day.tsx/shell.tsx), fix-engineer ved behov
related: [PC-ENT-02, PC-ENT-03]
---

## Kort
Når prøveperioden er udløbet (`GET /privat/subscription` → `status=expired, entitled=false`), siger Min dag intet om det. Der er ingen «Prøveperioden er slut» og ingen «Vælg plan». Headeren skifter stille fra «14 d» til «3 credits». Brugeren opdager først, at opkald og apps er væk, når de bliver afvist.

## Trin til at genskabe
1. Bruger i prøveperiode med en liste.
2. Lad prøveperioden udløbe (`trial_ends_at` i fortiden, ingen Stripe-sub). API: `expired`, `plan_status=expired`.
3. Åbn /privat/dag på 390 px.

## Forventet
PC-DAY-05: «Udløbet trial ser Dag: tydeligt "Prøveperioden er slut" + vælg plan; eksisterende data synlige. CTA til /privat/konto?planer=1; ingen fejlrøde bannere.» Teksten findes allerede: `plan.expiredLine` «Din prøveperiode er slut. Vælg en plan for at få opkald og alle apps igen.»

## Faktisk
Dag viser listen (godt) og et «Læg appen på hjemmeskærmen»-kort, men ingen udløbs-besked og ingen plan-CTA. `RoomCard` (day.tsx:186), der har «Vælg plan» for `!entitled`, vises ikke længere på Dag («The plan meter lives on Konto», ux-audit #2). Ring for mig, Delte lister og Ønskelister står stadig som slået til i bootstrap (se coverage §3.1, PC-ENT-02/03).

## Forslag
Når `plan_status === "expired"`: ét roligt kort øverst på Dag med `plan.expiredLine` og knappen «Vælg plan» → /privat/konto?planer=1. Plan-chippen i headeren kan sige «Prøve slut» i stedet for «3 credits».

## Evidens
- web/e2e/qa/privat-deep/core/dag-konto.spec.ts «PC-DAY-05» (fejler)
- qa/evidence/PC-DAY-05/PK-mobil-390-udloebet-dag.png (Dag uden udløbsbesked)

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
