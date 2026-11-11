---
id: F-PDEC-02-PC-WEBBOOK
scenario: PC-CALL / PC-ENT (browser-worker i Privat)
reported_by: qa-lead (beslutning Fürster 2026-11-11)
severity: S1
status: fixed
owner_fix: fix-engineer #10
related: [F-PDEC-01-PC-CALL-EXTRA]
---

## Kort
Beslutning: hjemmesidebooking (browser-worker: Privat booker et bord eller en tid på en hjemmeside for brugeren) er med i
alle planer. Uden plan er den ikke mulig. Der er et skjult fair use-loft. F-PDEC-01 havde givet den en omregnet credit-pris
på 2,90 kr. fra Opkaldssaldoen. Den pris er fjernet.

## Krav (fra qa-lead, 11/11)
1. **Med plan:** bookingen er inkluderet og tæller som en almindelig opgave. Den trækker intet fra Opkaldssaldoen og koster
   ikke 2,90 kr.
2. **Uden plan:** som «Ring for mig»: 409 `needs_plan` med CTA «Kræver en plan» → `/privat/konto`, i både API og UI.
3. **Fair use:** skjult loft på 30 pr. kalendermåned (Europe/Copenhagen) pr. workspace. Ved loftet kommer en venlig 429
   «Du har brugt månedens hjemmesidebookinger – prøv igen næste måned» på 8 sprog. Loftet vises aldrig som en pris og
   ligger i én konstant.
4. **Tekster:** ingen pris for hjemmesidebooking i prissider, app, fake-API eller docs. Den beskrives som «med i alle planer».

## Rodårsag
Der var ingen fejl. Det er en produktbeslutning. `browser/service.start_run` reserverede
`prices.PRIVAT_BROWSER_BOOKING_MINOR` (= 1 credit omregnet, 2,90 kr.) på Opkaldssaldoen, og `_settle_balance` trak den eller
frigav den. Routing-reglen `has_balance`/`no_balance` sendte brugere med tom saldo videre til telefonen. Der var ingen
plankontrol: uden plan betalte saldoen (velkomstbonus). Der var heller intet loft.

## Rettelse (commit 39d41cf)
- `app/modules/billing/prices.py`: `PRIVAT_BROWSER_BOOKING_MINOR` er fjernet. Ny konstant `PRIVAT_BROWSER_BOOKINGS_PER_MONTH = 30`,
  som også er `rules.BROWSER_BOOKINGS_PER_MONTH`. Den eksporteres ikke til prices.json.
- `app/modules/browser/service.py`: `require_allowed()` giver 409 `needs_plan` (extra `addon`, `plans`,
  `cta {label:"Kræver en plan", href:"/privat/konto"}`), og ved loftet 429 `browser_booking_limit`. `bookings_this_month()`
  tæller kørsler, der er startet i Københavns-måneden pr. workspace. `start_run` tager profil-låsen, så to samtidige starter ikke
  begge kan komme under loftet. Desuden sætter den `created_at=rules.now()`, `paid_by="plan"` og `usage_text` «Med i Plus» /
  «Med i prøveperioden». Ingen ledger-bevægelser. Ved fallback til telefon sættes `paid_by="call"`. `_release_old_hold` frigiver
  den gamle 2,90 kr.-reservation for kørsler, der blev startet før skiftet (idempotent).
- `app/modules/browser/routing.py`: `has_balance` og blokeren `no_balance` er fjernet.
- `app/modules/browser/assistant.py`: `tool_start_booking` og `_browser` kontrollerer `require_allowed` og sætter
  `_blocked()` i gang. Den skriver en `text`-besked med API'ets tekst og én markør i `options` (`cta:needs_plan` med
  `sub=/privat/konto` eller `notice:browser_booking_limit`, action `notice`). Hverken booking eller opkald startes, og saldoen
  betaler aldrig i stedet.
- `app/modules/privat/chat.py`: en markør med action `notice` kan ikke besvares (404).
- Web: `web/src/lib/privat/api.ts` (`NOTICE`) og `web/src/components/privat/chat.tsx`. Chatten viser `browser.needsPlanText`
  og knappen `call.needsPlan` («Kræver en plan») → `/privat/konto`, eller `browser.limit`.
  `privat.json` er opdateret på alle 8 sprog (`browser.needsPlanText`, `browser.limit`).
- Docs: pricing.md, privat-api.md, ADR-004-browser-worker.md og implementation-progress.md beskriver hjemmesidebooking som
  «med i alle planer» med fair use. Der står ingen pris. `privat/ledger.py`-docstringen er rettet.
- Fake-API (`web/src/lib/privat/fake.ts`) og prissider nævnte ikke hjemmesidebooking eller en pris for den. De er uændrede.

## Tests
- `tests/test_browser_booking_plan.py` har 14 tests. 13 er røde på 5ca402c og grønne efter. Den 14. (værktøjet `start_booking`
  tilbydes ikke uden plan) er en vagt-test, som også var grøn før.
  - Plan: ingen ledger-rækker, uændret saldo gennem hele kørslen, `paid_by=plan`. Tom saldo med Basis/Plus/Familie booker
    stadig online. En gammel reservation frigives én gang. Ingen pris i prices/service/export/docs.
  - Uden plan: `start_run` giver 409 `needs_plan` + CTA. Chat, hvor planen udløber midt i turen: CTA-markør, intet startet,
    intet opkaldsforslag. Markøren kan ikke besvares (404).
  - Loft: konstanten er 30. Den 31. giver 429 med den præcise tekst, og der er intet tal eller nogen pris i svaret. Grænsen
    for Københavns-måneden (31/10 23:30Z tæller i november, 22:30Z i oktober) er testet, og hvert workspace har sit eget loft.
    Chatten ved loftet er testet. Teksten findes på alle 8 sprog.
- Tilpasset: `tests/test_browser_assistant.py` (ingen saldo-bevægelser, tom saldo stopper ikke browsersporet) og
  `tests/test_browser_orchestrator.py`.
- Kørt på qa_fix10: `tests/test_browser*` 83 passed, `tests/test_privat*` 339 passed, ruff (app + ændrede tests) rent,
  `alembic check` rent (ingen migration), 4 × cmp ok (openapi, public-openapi, prices.json, addons-catalog.json), `tsc --noEmit`
  og `i18n:check` grønne.

## Beslutninger taget af fix-engineer (bekræft – needs-decision hvis uenig)
1. **Hvad tæller mod loftet:** alle startede kørsler i måneden, uanset udfald (også dem, der endte i telefon-fallback eller
   blev afvist), fordi en kørsel koster browser-tid, uanset hvordan den ender. Alternativet er kun gennemførte bookinger.
2. **Ved loftet:** assistenten skriver loft-teksten og starter intet. Den falder ikke selv tilbage til et opkald. Brugeren
   kan stadig skrive «ring», og opkald har deres egen kvote.
3. **Familie-husstand:** loftet gælder pr. workspace, som beslutningen siger. Hvert medlem har sit eget loft, ikke husstandens.
4. **Plan-tekst på opgaven:** «Med i Plus» / «Med i prøveperioden», samme ord som almindelige opgaver.

## Ikke gjort / mangler
- UI-markøren er kun testet via API og typecheck. Der er ingen e2e-spec, og web er ikke bygget, jf. opgaven.
- Chatbeskedens tekst fra serveren er dansk (som alle Privat-beskeder). Appen viser den oversatte tekst ud fra markøren.
- Der er ingen ny prisside-tekst om hjemmesidebooking. Prissiderne nævnte den ikke før. Hvis Fürster vil have «med i alle
  planer» på plankortene, kræver det tekst på 8 sprog, og det er hans beslutning.
- `ruff check` på hele `tests/` giver 30 fejl i `tests/qa/*`. De findes allerede på 5ca402c og er ikke rørt.
