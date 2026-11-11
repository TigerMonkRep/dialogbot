# ADR-004 — Browser-worker: en tøjlet browser-agent til booking på eksterne hjemmesider

Dato: 4. november 2026. Status: vedtaget for etape A (kode og tests); **ikke taget i drift** (se «Ikke eksternt verificeret»).
Navnet er ADR-004, fordi `docs/voice/ADR-003-voice-library.md` allerede findes.

## Kontekst

Privat-appens assistent skal kunne booke en tid hos en virksomhed, der ikke bruger Dialogbot, via virksomhedens offentlige
bookingside. Det er en handling på brugerens vegne på en tredjeparts hjemmeside. Tre ting må aldrig ske: agenten gør noget
andet end det, brugeren bad om; den forpligter noget (bekræfter, betaler, sender) uden et menneskeligt ja; og en hjemmeside kan
styre agenten (prompt-injektion) eller bruges til at nå vores interne net.

## Beslutninger

### 1. Playbooks før model

`browser_worker/playbooks/<motor>.py` er deterministiske Python-funktioner for én bookingmotor. En playbook kan teste, den kan
genafspilles til præcis samme punkt, og den koster ingen model-kald. Modellen (LLM-fallback, `llm_agent.py`) bruges kun, når motoren er
ukendt, eller en playbook-selector ikke rammer. Den får de samme syv værktøjer og de samme hårde grænser, men dens vej er ikke
deterministisk og kan **ikke genafspilles**: uden sin levende session går en LLM-kørsel til telefonsporet.

v1-motor: **OnlineBooq** (flowet ydelse → medarbejder → dato → tid → kontaktoplysninger → bekræft). Planway tilføjes som motor nr. 2 i en
senere etape. **Selectors og genkendelsessignaturer er ikke verificeret mod en rigtig OnlineBooq-side.** De er tekstmønstre i én
konfigurationsblok (`SELECTORS`) øverst i playbooken og i `SIGNATURES` i `engine_detect.py`, så en afvigelse rettes uden at røre logikken.
En selector, der ikke rammer, giver aldrig et gættende klik: den giver `PlaybookMiss` og dermed LLM-fallback eller telefon.

### 2. Allow-listen ligger i netværkslaget, i to lag

Prompt-injektion på en side kan ikke sende agenten et andet sted hen, fordi grænsen ikke er en instruktion, men en egenskab ved
browseren: (1) Chromium startes med en død proxy og en bypass-liste, der kun indeholder de godkendte værter. Browseren håndhæver den selv for
alle forespørgsler, også **omdirigeringer**, IP-adresser og WebSockets. Vi målte, at Playwrights `route()` ikke kaldes for omdirigeringshop
efter `continue_()`, så et `route()` alene ville lade en 302 til en fremmed vært slippe igennem. (2) `context.route` og `route_web_socket`
afviser det samme og logger det. Underdomæner af en listet vært er tilladt, forældredomæner er ikke.

### 3. Værter, der peger på interne adresser (DNS-rebinding)

Bookingsiden er i sidste ende under en fremmed virksomheds kontrol. Før en browser startes, slås hver tilladt vært op med
`app/core/safe_fetch.resolve_checked`, som afviser private, loopback-, link-local- og reserverede adresser samt cloud-metadata. Hvis en
adresse er intern, afvises kørslen med `error_code=unsafe_target`, og ingen browser starter. De kontrollerede adresser **pinnes** i Chromium
(`--host-resolver-rules=MAP <vært> <ip>`), så de ikke kan skifte midt i kørslen. Underdomæner kan ikke pinnes på forhånd; deres adresser
kontrolleres første gang siden bruger dem. **Restrisiko:** svaret kan være et andet ved selve forbindelsen. Derfor bør containeren desuden køre
uden adgang til cloud-metadata og interne net (Render-netværksindstilling). **Ikke eksternt verificeret.**

### 4. Forbudte felter og klik, i kode

`type`/`select` nægter felter, hvis `type`, `name`, `autocomplete`, label, `aria-label`, `placeholder` eller `id` matcher adgangskode, kortnummer,
CVC, udløb eller CPR (`failed`, `forbidden_field`). `click` nægter elementer, hvis tekst, `aria-label`, `value`, `title` eller billed-alt matcher en
liste af dansk/engelsk bekræft-ord (`limits.COMMIT_WORDS`) ved ordstart, medmindre kørslen er godkendt, og en godkendelse dækker **ét** klik.
Falske positive koster et ja eller et telefonopkald; et falsk negativ kunne forpligte noget, så listen er bevidst bred. «Fortsæt» og «Næste» er
ufarlige trin i en guide.

**Sikkerhedsnet:** en knap kan skjule bekræftelsen bag en uskyldig tekst. Fører et klik, der ikke blev stoppet, til en side, der ligner en
kvittering, og som ikke har en bekræft-knap tilbage, stopper kørslen med `unexpected_commit`. Opgaven går til `awaiting_user`, og brugeren får siden
og beskeden om, at bookingen kan være gennemført, og at virksomheden skal kontaktes for at aflyse. Efter et bekræft-klik siges der aldrig «intet er
booket» (`commit_unconfirmed`).

### 5. Ingen login og ingen CAPTCHA i v1

Et login ville kræve brugerens legitimationer; en CAPTCHA er en udtrykkelig markering af, at siden ikke vil have automatiserede klienter.
Begge giver `fallback_phone`, og der løses og logges intet ind. Det holder også v1 uden for de mest tvivlsomme vilkårsspørgsmål.

### 6. Godkendelsesgate

Agenten stopper ved bekræft-knappen. Brugeren får en `booking_proposal`-besked (egen beskedtype, så den aldrig forveksles med en betalings-`draft`)
med før→efter og Godkend/Afvis. Sessionen holdes i live i `BROWSER_APPROVAL_TTL_SECONDS` (ventetiden tæller ikke med i `max_seconds`).
Derefter lukkes browseren; et senere ja **genafspiller playbooken** og bekræfter kun, hvis dato, tid, ydelse, pris og navn er identiske med det,
brugeren godkendte, ellers vises et nyt forslag. Et ja ældre end 24 timer afvises. Alle skift, som to processer kan konkurrere om, er
compare-and-set, så en booking bekræftes højst én gang.

### 7. Genbrug i stedet for ny infrastruktur

Kø: den eksisterende outbox (`app/worker/runner.py`); browser-workeren henter kun `privat.browser_*`, hovedworkeren aldrig. Netværkshentning
af virksomhedens forside: `safe_fetch`. AI: `AIProvider` og `ai_usage` (formål `browser_agent`; omkostning gemmes i `browser_runs.cost_cents`
i USD-cent). Lager: privat Supabase-bucket (`BROWSER_EVIDENCE_BUCKET`), kun signerede links på få minutter.

### 8. Bevis

Skærmbillede pr. trin, det udfyldte forslag, slutsiden, kvittering som PDF og video. Videoen klippes med ffmpeg til `BROWSER_MAX_SECONDS`, før den
uploades; kan den ikke klippes, uploades den ikke. Lokale filer slettes efter kørslen. Optagelsen kører, mens brugeren tænker, så den viser kun de
første `max_seconds`; forslagsbilledet, slutbilledet og PDF'en dækker resten. Der findes ingen billeder af udfyldte forbudte felter, fordi de aldrig
udfyldes.

### 9. Hvordan en kørsel startes fra chatten (A5)

Modellen siger kun, **hvad brugeren vil** (virksomhed, ydelse, tidsvinduer og kun det, brugeren selv sagde om «ring» eller «skriv»). **Koden vælger
sporet** (`app/modules/browser/routing.py`), i denne rækkefølge: (1) brugeren sagde «ring» → telefon, «skriv» → browser, hvis det kan lade sig gøre
(ellers telefon, og vi siger hvorfor), uden spørgsmål; (2) ønsket er ikke «book» (flyt/aflys er ikke automatiseret i v1) → telefon; (3) hjemmeside
fundet, motor kendt og tilladt, bookingadresse findes, og brugeren har navn og bekræftet mobil på profilen → browser (kræver også, at workeren er
slået til, og at bookingprisen er på Opkaldssaldoen); (4) ellers telefon. Assistenten **siger altid, hvilket spor** den tager («Jeg prøver at booke online hos X – du får et
forslag at godkende» / «Jeg ringer til X i åbningstiden, når du har godkendt opkaldet»). Enhver fejl i browsersporet giver et færdigt opkaldsforslag
uden et ekstra «skal jeg ringe?», men opkaldet kræver stadig brugerens almindelige godkendelse, fordi et opkald er en handling med omkostning. «Ring i
stedet» stopper en kørsel, der endnu ikke har trykket bekræft, og frigiver reservationen; efter bekræft-klikket kan den ikke fortrydes (`browser_run_confirming`).

**Hvad en kørsel aldrig må:** starte uden en konkret booking (ydelse + mindst én dateret tidsramme; ellers spørger assistenten), og udfylde andet end brugerens
eget navn og bekræftede mobilnummer (aldrig e-mailadressen).

**Opslag** (`lookup.py`, værktøjet `find_business`): CVR-registret (navn, adresse, telefon, CVR-nummer, `reklamebeskyttet`), derefter Google Places (hjemmeside,
åbningstider; telefon kun som fallback). **Hjemmesiden kommer kun fra Google**; CVR-registrets «hjemmeside»-felter bruges ikke. Uden `GOOGLE_PLACES_API_KEY`
springes hjemmeside-opslaget over, og sporet bliver telefonen. Resultatet gemmes i `external_business_contacts`, så det samme opslag ikke betales to gange; Googles
indhold (hjemmeside, åbningstider) droppes efter `GOOGLE_PLACES_CACHE_DAYS`, kun `place_id` bliver. Opslag i CVR på navn er **ikke eksternt verificeret**.

**Pris:** en browser-booking koster 2,90 kr. fra Opkaldssaldoen (`BROWSER_BOOKING_MINOR` = den tidligere ene credit omregnet med 2,90 kr.; F-PDEC-01 – egen pris er ikke besluttet). Reserveres ved start, bruges når kørslen ender i en
booking (eller i et klik, der kan have booket), frigives ellers. Prisen er den samme for alle, også med en plan; det er ikke afgjort, om en plans
opkaldskvote skal gælde for browser-bookinger.

## Juridisk forbehold

Agenten handler **på brugerens vegne** på offentlige bookingsider, og brugeren godkender hver booking. Det er ikke afklaret, om det er i
overensstemmelse med hver bookingmotors og hver virksomheds **vilkår (ToS)**, herunder forbud mod automatiserede klienter, og med lovgivningen om
adgang til data. **Vilkårene for hver motor skal gennemgås af en jurist, før `BROWSER_WORKER_ENABLED` sættes i prod.** Samme gælder behandlingen af
evidens (skærmbilleder og video kan indeholde brugerens navn og telefonnummer): opbevaringstid og sletning er endnu ikke fastlagt.

## Ikke eksternt verificeret

- Ingen rigtig bookingside: alt er testet mod lokale HTML-kloner. Selectors og motor-signaturer er gæt ud fra det offentlige flow.
- Ingen rigtig Supabase Storage: signering er testet med en stub; lokal lagring bruges i test.
- Ingen rigtig AI-udbyder i tests (en scriptet stand-in). Kvaliteten af LLM-fallback er ikke målt.
- DNS-rebinding-forsvaret er testet med en simuleret resolver og med pinning mod en lokal server; netværksindstillingen uden adgang til
  cloud-metadata er ikke indstillet eller verificeret.
- Render-tjenesten er skrevet, men ikke deployet.
