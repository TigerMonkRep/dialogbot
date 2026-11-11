---
id: F-PX-05-PC-I18N-02
scenario: PC-I18N-02
reported_by: i18n-a11y-qa (PX)
severity: S2
status: fixing
owner_fix: ui-ux-engineer
related: [PC-I18N-01]
---

## Kort
På en/de vises danske backend-tekster i Butik, Butik-detalje og Kalender: appens «Hvad den gør» (`what`), taglines, «Det skal den bruge» (`needs`) og eksempelsætningen. web har oversættelser (`addons.<key>.*` i privat.json), men `a.what || addonText(…)` foretrækker backendens danske tekst.

## Trin til at genskabe
1. Plus-bruger, cookie dlg_lang=de (eller en), desktop-1440.
2. Åbn /privat/butik, /privat/butik/pakker, /privat/kalender, /privat/butik/ring-for-mig.

## Forventet
coverage.md §3.14 + PC-I18N-01: ingen dansk UI-tekst i andre sprog undtagen dokumenteret backend-indhold. Butikken er UI, ikke brugerindhold.

## Faktisk (uddrag, qa/evidence/PX/i18n-app-desktop-1440.json)
- de:/privat/butik: «Glem aldrig en fødselsdag igen», «Ugens aftensmad – og indkøbslisten følger med», «Syn, service og dæk – Peter holder styr på bilen» …
- en+de:/privat/butik/pakker: «Giv Peter dit track-and-trace-nummer, så holder han øje med pakken …»
- en+de:/privat/kalender: «De tider, Peter aftaler for dig … lander i din egen kalender …»
- de:/privat/butik/ring-for-mig: «Sag z. B. „Ring til cykelværkstedet og find en tid torsdag efter klokken tre“»
Mobil-390 viste ingen af dem på de samme ruter (andet layout).

Øvrige backend-tekster, der forbliver danske (dokumenteret, kendt begrænsning): fejlbeskeder (`ApiError.message` vises direkte i 29 steder i components/privat, fx apps.tsx setErr(x.message)), chat-svar og opkaldsbeskeder, parcels/travel status- og pristekster (`price_note` «samlet pris for alle rejsende»), SMS-invitationsforslag. Hårdkodet dansk i web: wishes.tsx `errText` fallback «Noget gik galt. Prøv igen.», invitation opengraph-image «… har delt sin ønskeliste med dig».

## Evidens
- web/e2e/qa/privat-deep/x/i18n.spec.ts («app-skærme på en/de»), qa/evidence/PX/i18n-app-*.json, i18n-de-butik-rfm-*.png
- tests/qa/test_qa_pd_x.py::test_px_i18n_02_backend_texts_are_danish_only (dokumenterer at API'et altid svarer dansk)

## Forslag
Brug `addonText`-oversættelsen først for name/tagline/description/what/needs/example (backend-teksten kun som fallback), og oversæt `errText`-fallback + OG-billedet.

## Rodårsag / Rettelse / Verifikation

## Rettelse (udfyldes af fix-engineer)
- Delvist: ny helper addonWhat(t, a, locale) i web/src/components/privat/addons.tsx – på andre sprog end dansk vinder den oversatte beskrivelse over backendens danske `what`. Brugen i apps.tsx (ui-ux's fil) er overdraget via qa/ledger.md.
- Rest: backendens needs/example/steps (addons.py) er kun på dansk og kræver i18n-nøgler i privat.json (addons.<key>.needs/example/steps) eller backend-oversættelse.
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)
- Fix-engineer #5 (2026-11-11): invitationens OG-billede er ikke længere hårdkodet dansk – det følger invitationens sprog (`lang` i GET /privat/invites/{token} = afsenderens sprog; nøgler privat.inviteOg.* ×8). Test: tests/test_privat_sharing.py::test_invite_preview_leaks_nothing (lang). Fundet forbliver «fixing» for apps.tsx/needs/example.
