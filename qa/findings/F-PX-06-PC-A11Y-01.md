---
id: F-PX-06-PC-A11Y-01
scenario: PC-A11Y-01
reported_by: i18n-a11y-qa (PX)
severity: S2
status: new
owner_fix: ui-ux-engineer
related: []
---

## Kort
axe (wcag2a/aa, 21, 22) finder «serious» på alle indloggede Privat-skærme (begge viewports): label-content-name-mismatch (WCAG 2.5.3 Label in Name) og på /privat/konto (desktop) color-contrast.

## Trin til at genskabe
1. Plus-bruger, åbn /privat/dag, /samtale, /opgaver, /apps, /butik, /butik/<key>, /folk, /konto, /kalender, /apps/ring-for-mig.
2. Kør axe-core (web/e2e/qa/privat-deep/x/a11y-pwa.spec.ts «PC-A11Y-01»).

## Faktisk
- Logo-link i Privat-shell: `<a aria-label="Dialogbot Privat – Min dag" href="/privat/dag">` – synlig tekst «Dialogbot PRIVAT» indgår ikke i navnet i samme form (alle app-skærme).
- Kontomenu: `<button aria-label="Kontomenu">` viser initialer «MH».
- Plan-chip: `<button aria-label="Din plan: Plus · prø…">` viser «14 d».
- /privat/konto (desktop-1440): color-contrast på 2 knapper (`.flex-wrap.gap-2:nth-child(4) > button:nth-child(1)` med aria-expanded, og en `min-h-[52px]`-knap).
Taleskyde-brugere («klik Dialogbot», «klik 14 d») rammer ikke elementerne.

## Gentest på 451d53b (22:10Z)
label-content-name-mismatch er stadig på alle 11 app-skærme (logo-link + kontomenu `.w-11`); color-contrast på /privat/konto er væk. Plan-chippen optræder ikke længere.

## Forventet
PC-A11Y-01: axe 0 kritiske/alvorlige.

## Øvrige målinger (ikke fejl, input til design)
- Desktop-topnavigation (Min dag, Mine opgaver, Apps, Folk, Konto) er 38 px høj (< 44 px-målet); landing /privat: «Erhverv» 32 px, «Send» 38 px, «Månedligt» 40 px.
- Brødtekst < 16 px: /privat/butik 59 af 60 tekstblokke er 15 px (taglines/beskrivelser); /privat/apps 10/11.
- Ingen vandret scroll på 390 px eller ved 200 % zoom (195 css-px) på Dag, Butik, Butik-detalje, Konto. ✔
- PlanSheet: fokus i dialog, Tab bliver inde, role=radiogroup, Escape lukker. ✔
- Ord over folden (mobil 390, PC-BRAND-03): Dag 43, Butik 124, Butik-detalje (ring-for-mig) 98, Konto 86, Kalender 123, landing 101; én primær knap på Dag/Butik-detalje, 0 på Butik/Konto.

## Evidens
- qa/evidence/PX/a11y-mobil-390.json, a11y-desktop-1440.json

## Forslag
Navngiv logo-link «Dialogbot Privat» (evt. sr-only «– Min dag» efter den synlige tekst), kontomenu `aria-label="MH – Kontomenu"`, plan-chip med synlig tekst først («14 d – din plan: Plus …»); ret kontrasten på de to Konto-knapper.

## Rodårsag / Rettelse / Verifikation
