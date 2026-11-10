---
id: F-PK-03-PC-SEC-03
scenario: PC-SEC-03
reported_by: e2e-privat (PK)
severity: S1
status: fixed
owner_fix: fix-engineer (ui-ux-engineer ejer shell.tsx-layoutet; koordinér)
related: []
---

## Kort
Når Privat-API'et svarer 403 `privat_not_enabled` (lukket pilot, flag slået fra, deploy uden backend), skifter web stille til simuleringen i browseren. På mobil (390 px) er «Simuleret»-mærket skjult. Den indloggede bruger ser en falsk «14 d»-prøveperiode og «1 af 10 opkald i Plus», og «Svar» på et opkald til Tandlæge Holm, samt grupper og invitationer i Mine folk, uden noget mærke. Kun Konto viser «SIMULERET».

## Trin til at genskabe
1. Log ind som en rigtig bruger på :3400 med mobil-viewport 390.
2. Lad `/api/backend/privat/**` svare 403 `{"code":"privat_not_enabled"}`. Det svarer til en konto uden for PRIVAT_ALLOWED_EMAILS eller PRIVAT_ENABLED=false (`isUnavailable` i web/src/lib/privat/api.ts:576).
3. Besøg /privat/dag, /privat/opgaver, /privat/samtale, /privat/butik og /privat/folk.

## Forventet
PC-SEC-03: «Brugeren må ikke tro, at handlinger (opkald, betaling, invitationer) er udført. «Simuleret»-mærke synligt overalt. Uden mærke → fund S1.»

## Faktisk
- Mobil 390: der er intet «Simuleret» på Dag, Opgaver, Samtale, Butik og Folk. `shell.tsx:125` renderer `{simulated && <span className="hidden sm:inline-flex"><Sim /></span>}`, så mærket er skjult under 640 px. Dag viser plan-chippen «14 d» og «1 af 10 opkald i Plus». Kun små «Eksempel»-pills på demo-kortene.
- Desktop 1440: mærket ses i headeren (testen består).
- Konto viser «SIMULERET · Privat-API'en er ikke slået til endnu …» på begge viewports.

## Forslag
Vis `<Sim />` i headeren på alle bredder. Det kan fx erstatte plan-chippen, når `simulated`. Eller vis et fast banner øverst i `(app)/layout`, når `simulated && loggedIn`. En logget-ind bruger bør helst få en ærlig «Dialogbot Privat er ikke åbnet for din konto endnu»-side i stedet for simuleringen (needs-decision hos Fürster). Se også PC-ACC-08.

## Evidens
- qa/evidence/PC-SEC-03/PK-mobil-390-{dag,opgaver,samtale,butik,folk,konto}.png
- qa/evidence/PC-SEC-03/PK-desktop-1440-*.png (består)
- Test: web/e2e/qa/privat-deep/core/sikkerhed.spec.ts (fejler på mobil-390, består på desktop-1440)

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Dublet af F-PS-07 (samme rod, store.tsx). Se F-PS-07. Mobil-mærket rettet af ui-ux-engineer (shell.tsx).
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
