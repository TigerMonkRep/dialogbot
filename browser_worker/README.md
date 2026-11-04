# Dialogbot browser worker

En **tøjlet browser-agent**, der kan booke, flytte og aflyse tider på virksomheder, som ikke bruger Dialogbot, via deres
offentlige bookingside. Den gør kun det, brugeren bad om, kun på godkendte domæner, og den trykker aldrig på
«Bekræft/Book/Betal/Send» uden et menneskeligt ja i Privat-appen. Kan den ikke, falder opgaven tilbage til
telefonsporet (`call`-opgaven i Privat).

Beslutningerne står i [`docs/ADR-004-browser-worker.md`](../docs/ADR-004-browser-worker.md).

> **Status (A1–A2):** kernen (netværksvagt, de syv værktøjer, forbudte felter og klik, CAPTCHA/login, budget,
> sikkerhedsnet mod uskyldigt mærkede bekræft-knapper), OnlineBooq-playbook og motor-genkendelse er bygget og testet mod en
> lokal HTML-klon. Godkendelsesgate, endpoints, LLM-fallback, bevis-upload og drift kommer i A3–A4 (se
> `docs/implementation-progress.md`, checkpoint 30).
> **Ikke verificeret mod nogen rigtig bookingside.** Alt er testet mod `tests/sites/onlinebooq/`, en klon bygget ud fra
> OnlineBooqs offentlige flow (ydelse → medarbejder → dato → tid → kontaktoplysninger → bekræft). Selectors og
> genkendelsessignaturer er derfor **ikke** bekræftet mod en rigtig side.

## De syv værktøjer (og intet andet)

| Værktøj | Hvad |
|---|---|
| `navigate(url)` | Åbn en adresse. Adressen skal ligge på et godkendt domæne |
| `read_page()` | Siden som kompakt tekst (rolle, navn, tilstand, `[eN]`-ref). Aldrig HTML. Adgangskodeværdier returneres aldrig |
| `click(ref)` | Klik. Nægter «Bekræft/Book nu/Gennemfør/Betal/Send/Confirm/Submit/Pay/Complete …», medmindre kørslen er godkendt |
| `type(ref, text)` | Udfyld et felt. Nægter adgangskode, kortnummer, CVC, udløb og CPR |
| `select(ref, value)` | Vælg i en rulleliste (samme feltvagt) |
| `wait(ms)` | Vent (højst 5 s pr. kald) |
| `screenshot()` | Gem et billede |

`ref` kommer altid fra det **seneste** `read_page()`; en gammel ref afvises. Hvert kald tæller som ét trin, logges i `steps`
med tidsstempel og screenshot.

## Hårde grænser (kode, ikke prompt)

1. **Netværks-allow-liste, to lag.** (1) Chromium startes med en død proxy og en bypass-liste, der kun indeholder de
   godkendte værter (`netguard.chromium_args`). Det håndhæves af browseren selv for alle forespørgsler, **også
   omdirigeringer og IP-adresser** (Playwrights `route()` kaldes ikke for omdirigeringshop, det er testet). (2) `context.route("**/*")` og
   `route_web_socket` afviser alt uden for listen og logger det. Subdomæner af en listet vært er tilladt, forældredomæner
   er ikke. **Prompt-injektion på siden kan derfor ikke sende agenten (eller dens data) et andet sted hen.**
2. **Forbudte felter** (`type`, `name`, `autocomplete`, label, `aria-label`, `placeholder`, `id`): password, kortnummer, cvc, udløb, cpr
   → `failed`, `error_code=forbidden_field`. Feltet røres ikke, og der findes derfor aldrig screenshots af udfyldte forbudte felter.
3. **Forbudte klik** (synlig tekst, `aria-label`, `value`, `title`, billed-alt): se `limits.COMMIT_WORDS`. Uden godkendelse →
   `awaiting_approval`. En godkendelse dækker **ét** bekræft-klik; et andet giver `commit_limit`.
4. **CAPTCHA og login** (iframe/script fra kendte CAPTCHA-udbydere, `.g-recaptcha`/`data-sitekey`, synligt password-felt,
   «du skal være logget ind») → `fallback_phone`. Der løses intet og logges intet ind.
5. **Budget:** `max_steps` (standard 25) og `max_seconds` (standard 180) → `fallback_phone`.

Grænserne er mønstre og kode i `limits.py`, `netguard.py` og `session.py`. Mønstrene matcher ordstart (så «Algemene» ikke
rammes af «gem»). Falske positive koster et menneskeligt ja eller et telefonopkald; et falsk negativ kunne forpligte noget.
Ved tvivl udvides listen.

## Playbooks først, model som fallback

`playbooks/<motor>.py` er en deterministisk Python-funktion for én bookingmotor. Den navigerer til «udfyldt, men ikke
bekræftet» (`prepare(session, goal, start_url)` → `Prepared.before_after`) og bekræfter først, når kørslen er godkendt
(`confirm(session)`). Den bruger kun sessionens syv værktøjer og dermed alle de hårde grænser.

**v1-motor: OnlineBooq** (`playbooks/onlinebooq.py`). Valgt som den motor, vi kan modellere ud fra det offentlige flow:
ydelse → medarbejder (valgfri) → dato → tid → kontaktoplysninger → bekræft. Playbooken genkender selv, hvilket trin der er på
skærmen (og springer et manglende trin over). Kun `book` er automatiseret; `flyt`/`aflys` giver `PlaybookUnsupported`
(→ LLM-fallback/telefon). Planway tilføjes som motor nr. 2 i en senere etape.

> **Selectors er ikke verificeret mod en rigtig OnlineBooq-side.** De ligger i én konfigurationsblok, `SELECTORS`, øverst i
> filen: tekstmønstre (regex) på elementernes navn, ikke CSS. Findes en afvigelse på en rigtig side, rettes den dér uden at røre
> logikken. En selector, der ikke rammer, giver `PlaybookMiss` (→ LLM-fallback), aldrig en gætte-klik.

Tre udfald, som kalderen skelner mellem:
- `PlaybookMiss(reason, found)` – en selector/et trin virkede ikke, eller intentionen understøttes ikke → LLM-fallback.
- `NoAvailability(found)` – siden virker, men intet passer til brugerens tidsvinduer → `fallback_phone` med det fundne
  (ydelse, datoer og tider set), så telefonsporet starter klogere.
- Terminale udfald fra sessionen (`RunFailed`, `FallbackPhone`, `ApprovalRequired`) går uændret igennem.

**Ny playbook (motor nr. 2 og 3):**
1. Kopiér `playbooks/onlinebooq.py` til `playbooks/<motor>.py`; ret `ENGINE` og `SELECTORS`, og tilpas trinnene, hvis flowet er
   anderledes.
2. Registrér den i `playbooks/__init__.py` (`REGISTRY`).
3. Tilføj motorens signatur til `SIGNATURES` i `engine_detect.py` (script-/iframe-/link-adresse), og tilføj motornøglen til
   `BROWSER_ALLOWED_ENGINES`.
4. Byg en statisk klon i `tests/sites/<motor>/` (flere sider, formular, bekræft-knap, kvittering) og kopiér testene fra
   `tests/test_playbook_onlinebooq.py`.

**Motor-genkendelse** (`engine_detect.py`): henter virksomhedens forside og højst to sider, som er linket med ord som
«book/booking/bestil tid» (kun samme website), og leder efter motorens adresse i script, iframe, formular og links. Resultatet
huskes pr. website i `business_booking_profiles` (90 dage; «unknown» tjekkes igen efter 7). Hentningen går gennem
`app/core/safe_fetch.py` (adresser slås op og kontrolleres, robots.txt overholdes). **Signaturerne er ikke verificeret mod
rigtige sider.**

**Sikkerhedsnet:** et klik, der ikke blev stoppet af ordlisten, men som fører til en side, der ligner en kvittering uden en
bekræft-knap tilbage («tak for din booking», «din tid er booket», «bekræftelse», «kvittering» …), giver `failed` med
`error_code=unexpected_commit`, og URL + screenshot gemmes, så brugeren kan aflyse. Det fanger en «Næste»-knap, der i
virkeligheden booker. Det er et sikkerhedsnet, ikke en erstatning for godkendelsen: bookingen kan allerede være gennemført.

## Kør tests (ingen netværk)

```bash
pip install -r requirements.lock -r browser_worker/requirements.lock
playwright install --with-deps chromium      # lokalt; i en container med forhåndsinstalleret Chromium: BROWSER_CHROMIUM_PATH=…
pytest -p no:cacheprovider -c /dev/null --rootdir . browser_worker/tests
```

Testene serverer `tests/sites/<motor>/` fra en lokal server (`tests/site_server.py`) og rører aldrig en rigtig hjemmeside.
Videooptagelse kræver Playwrights ffmpeg (`playwright install ffmpeg`, følger med `--with-deps chromium`-trinnet i CI).

## Drift

Image: `browser_worker/Dockerfile` (bygges fra rodmappen; basisimagets tag skal følge `playwright` i `requirements.lock`).
Én Playwright-browsercontext pr. kørsel; ingen delt tilstand mellem kørsler. Lokale filer (screenshots, video) slettes efter upload.
