---
id: F-PFX-03-PC-APP-01
scenario: PC-APP-01
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S1
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Garanti lovede «Gemmer ikke billeder af kvitteringer», men appen gemmer kvitteringsfoto (POST apps/garanti/items/{id}/photo).

## Rettelse (udfyldes af fix-engineer)
- Rettelse: teksterne fortæller nu sandheden. Tilladelsen lyder «Gemmer et foto af kvitteringen, hvis du selv tilføjer ét – det slettes med tingen eller appens data» (delete_data og remove sletter allerede fotoet). «Hvad den gør» og chat-svaret siger «Tilføj gerne et foto af kvitteringen» i stedet for «Gem selv kvitteringen».
- Filer: app/modules/privat/addons.py, app/modules/privat/chat.py, web/src/lib/privat/addons-catalog.json (regenereret; cmp-check OK)
- Bemærk: F-PS-08 (kvitteringsfoto med GPS-metadata) er ikke rørt.
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: addons.py garanti.permissions siger nu «Gemmer et foto af kvitteringen, hvis du selv tilføjer ét …»; addons-catalog.json cmp OK
- Fejler testen uden rettelsen? ja – f2b3d11 har «Gemmer ikke billeder af kvitteringer»
- Naboscenarier kørt: cmp addons-catalog.json
- Dom: closed
