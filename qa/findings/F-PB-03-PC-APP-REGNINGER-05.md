---
id: F-PB-03-PC-APP-REGNINGER-05
scenario: PC-APP-REGNINGER-05
reported_by: e2e-privat (PB)
severity: S2
status: new
owner_fix: ui-ux-engineer (apps.tsx) / fix-engineer
related: [PC-APP-MADPLAN-05, PC-APP-KALENDER-05, PC-APP-KAELEDYR-05, PC-APP-LAEGE-OG-TANDLAEGE-05, PC-APP-OENSKELISTER-05, F-UX-04]
---

## Kort
«Slå til igen» på en app, der er slået fra med data gemt, giver ingen bekræftelse. Arket «X er slået til – Alt, den havde gemt, er her igen» (`apps.enabledKept`) bliver aldrig vist.

## Trin til at genskabe
1. Prøve-konto, slå Regninger til og gem en regning.
2. Appens side → «Slå fra» → bekræft.
3. /privat/apps/regninger → «Slå til igen» → «Slå til».
4. Arket lukker med det samme, og siden viser appen som slået til. Det gælder alle apps.

## Forventet
Scenarie PC-APP-*-05: «geninstallér viser «enabledKept» og gamle data». EnableSheet har grenen `kept` netop til det.

## Faktisk
I `AppPage` renderes `<EnableSheet>` kun i grenen `if (!a.enabled)` (web/src/components/privat/apps.tsx:620-650). `enable()` kalder `refresh()`, før den sætter `state="done"`. Derfor skifter siden til den slåede-til-visning, og arket afmonteres, før bekræftelsen når at blive vist. Data er korrekt tilbage (verificeret via API). Desuden starter siden igen på «Trin 1 af 3», selvom appen har data (samme som F-UX-04).

## Evidens
- Browser: web/e2e/qa/privat-deep/apps-b/*.spec.ts «-05» (soft-assert «F-PB-03 enabledKept»), screenshot qa/evidence/PC-APP-REGNINGER-05/
- Playwright error-context: /home/claude/pd-results/PB/*Slet-data*/error-context.md

## Forslag
Render EnableSheet uden for `!a.enabled`-grenen (som `DisableSheet` i den slåede-til-gren), eller vis en toast «Regninger er slået til igen – dine data er her stadig».

## Rodårsag (udfyldes af fix-engineer)

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
