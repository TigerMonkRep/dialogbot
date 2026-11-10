---
id: F-PB-04-PC-APP-OENSKELISTER-01
scenario: PC-APP-OENSKELISTER-01
reported_by: e2e-privat (PB)
severity: S2
status: fixed
owner_fix: ui-ux-engineer (apps.tsx) – evt. needs-decision (Fürster)
related: [PC-APP-RING-FOR-MIG-01, PC-APP-DELTE-LISTER-01]
---

## Kort
Apps, der er slået til fra start (Ønskelister og Delte lister for alle, Ring for mig med prøveperiode/plan), står ikke længere i Butikken. Deres ikon under Mine apps åbner app-siden, som ikke har «Hvad den gør». En ny bruger kan derfor aldrig læse, hvad appen gør.

## Trin til at genskabe
1. Ny prøve-konto.
2. /privat/butik: Ønskelister og Ring for mig står ikke på listen (build 22:03, `avail = all.filter(a => !a.enabled && !a.disabled_at)`, apps.tsx:142).
3. /privat/apps → Ønskelister → /privat/apps/oenskelister: kun opsætning, «Spørg Peter», tilladelser (sammenklappet) og «Slå fra». Ingen «Hvad den gør» (`AboutApp` bruges kun på butiks- og kept-siden, apps.tsx:308/633).

## Forventet
Fürsters beslutning (qa-brief-privat.md): «Butikken: hvert app-ikon fører til "Hvad den gør" og videre til appens egen installér-flow.» Scenarie PC-APP-*-01.

## Faktisk
For de standard-apps findes der intet sted i UI'et med «Hvad den gør»-teksten (`what`) fra API'et.

## Evidens
- Browser: web/e2e/qa/privat-deep/apps-b/oenskelister.spec.ts og ring-for-mig.spec.ts «-01» (soft-assert «F-PB-04»), screenshots qa/evidence/PC-APP-OENSKELISTER-01/PB-*-app-page-trial.png

## Forslag
Vis `what` øverst på app-siden (én linje), eller behold slåede-til apps i Butikken med mærket «Slået til». Hvis det er bevidst at skjule dem, så er det en needs-decision til Fürster.

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- ui-ux-engineer (fase 2, punkt 2): apps.tsx – app-siden har «Om appen»-fold med «Hvad den gør» + «Den får lov til» for ALLE apps; Butikken linker «N apps er slået til – se Mine apps»
- Filer:
- Commit:
