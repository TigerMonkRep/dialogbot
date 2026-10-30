# Besøgsstatistik på dialogbot.dk

To kilder, begge vist under **Operator → Admin → Hjemmeside** (`/app/operator/admin/hjemmeside`).

| | Vercel Web Analytics | Google Analytics 4 |
|---|---|---|
| Hvem tælles | Alle besøgende | Kun dem, der siger ja i cookie-banneret |
| Cookies | Ingen | Statistikcookie (`_ga`) |
| Script | `@vercel/analytics` i `web/src/components/site-analytics.tsx` | `gtag.js`, indlæses først efter samtykke |
| Dashboard | <https://vercel.com/rene-simonsens-projects/dialogbot/analytics> | <https://analytics.google.com/> |
| Backend-læsning | `VERCEL_API_TOKEN` (+ `VERCEL_PROJECT_ID`, `VERCEL_TEAM_ID`, har defaults) | `GA4_PROPERTY_ID` + `GA_SERVICE_ACCOUNT_JSON` |

Ingen af scripts kører på `/app`, `/login`, `/signup` eller `/gastrohall`. Samtykket gemmes i `localStorage` (`db-consent`);
"Cookieindstillinger" i sidefoden nulstiller det. Privatlivssiden beskriver begge kilder.

## Opsætning

**Vercel**
1. vercel.com → projektet *dialogbot* → *Analytics* → *Enable*.
2. Account → *Tokens* → nyt token (scope: teamet). Læg det som `VERCEL_API_TOKEN` på backend-tjenesten i Render.

**Google Analytics**
1. analytics.google.com → opret GA4-ejendom for dialogbot.dk → *Administrer → Datastreams* → kopiér målings-id (`G-…`).
2. Vercel → projektet → *Settings → Environment Variables* → `NEXT_PUBLIC_GA_MEASUREMENT_ID` = `G-…` (Production) → redeploy.
3. For tal i admin: Google Cloud → servicekonto, slå *Google Analytics Data API* til, hent JSON-nøgle. I GA4: *Administrer → Adgangsstyring* → tilføj servicekontoens e-mail som *Læser*.
4. Render → `GA4_PROPERTY_ID` (numerisk, står under *Administrer → Ejendomsindstillinger*) og `GA_SERVICE_ACCOUNT_JSON` (hele nøglen på én linje).

## Backend

`GET /api/v1/operator/analytics/website?days=7|30|90` (kun platformsoperatører). Svaret har `vercel` og `ga`, hver med
`configured`, `error` og tallene (`visitors`/`users`, `pageviews`, `by_day`, `pages`, `referrers`/`sources`, …).
Resultater caches i 10 minutter (`app/modules/analytics/service.py`). Google-adgangen signerer selv sit OAuth-JWT med
PyJWT – ingen Google-SDK. Der læses kun tal, aldrig noget om enkelte besøgende.
