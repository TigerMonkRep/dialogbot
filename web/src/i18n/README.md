# Sprog i web (i18n)

Sprog: `da` (kilde), `en`, `de`, `es`, `fr`, `it`, `no` (bokmål), `sv`. Konfiguration i `config.ts`.

## Ruter
- Markedsføringssider (listen i `config.ts → isPublicPage`) findes pr. sprog under `/<sprog>/…`, fx `/de/priser`.
  Filerne ligger stadig uden præfiks (`src/app/priser/page.tsx`); `src/proxy.ts` omskriver og sender sproget videre.
- App, login, opsætning osv. har ingen præfiks; sproget er brugerens valg (cookie `dlg_lang`).
- dialogbot.dk og www.* viderestilles til dialogbot.app (dansk forside → `/da`).

## Tekster
- Én JSON pr. namespace pr. sprog: `messages/<sprog>/<namespace>.json`. Namespaces står i `config.ts → NAMESPACES`.
- Dansk skrives først; de andre sprog oversættes fra dansk og har PRÆCIS samme nøgler.
- Nøgler: engelske camelCase, grupperet pr. side/komponent: `"pricing": { "title": "…", "faq": [ … ] }`.
- Variabler: `"Hej {name}"` → `t("x", { name })`. Flertal: `"{n|én samtale|# samtaler}"` (1 → første form, ellers anden;
  `#` = tallet).
- Lister/objekter (FAQ, punkter, tabeller): læg dem i JSON som arrays/objekter og hent med `raw<T>("ns.key")`.
- Ingen HTML i JSON. Fed/links i en sætning: del sætningen i stykker (`intro.before`, `intro.link`, `intro.after`).
- Brand og produktnavne oversættes ikke: Dialogbot, Peter. Telefonnummer, e-mail, CVR uændret.
- Priser: beløb og valuta står som i dag (kr., ekskl. moms) i alle sprog – kun ordene oversættes.

## I kode
- Serverkomponent: `const t = await getT("site");` (`@/i18n/server`). Rå værdier: `const raw = await getRaw();`.
- Klientkomponent (`"use client"`): `const t = useT("app");` (`@/i18n/client`), `useRaw()`, `useLocale()`.
- Links: `import Link from "@/i18n/link"` i stedet for `next/link` – markedsføringssider får selv sprogpræfiks.
- Metadata: `export async function generateMetadata()` med `getT` i stedet for en statisk `metadata` med danske tekster.
- Datoer/tal: `new Intl.DateTimeFormat(HTML_LANG[locale], …)` i stedet for hårdkodet `"da-DK"`.
- Operatør-sider (`/app/operator/**`) forbliver danske (kun Dialogbots egne operatører bruger dem).

Efter en ny namespace-fil: `node scripts/i18n-index.mjs`. `npm run i18n:check` sammenligner nøgler på tværs af sprog.
