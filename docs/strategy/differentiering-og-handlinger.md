# Differentiering: sådan skiller Dialogbot sig ud på det danske marked

Dato: 29. september 2026. Grundlag: `reports/Danske AI telefonassistenter benchmark.md` og kodebasen pr. commit `5d657fd`.

## 1. Udgangspunkt fra benchmarken

- 20+ danske udbydere sælger det samme: indgående telefonsvar + booking + resumé, afregnet som abonnement med inkluderede minutter og 1–2,5 kr./min i overforbrug.
- Alle køber den samme amerikanske stak (ElevenLabs/Vapi/Deepgram/OpenAI/Twilio) til 0,6–0,9 kr./min. Ingen har egen dansk stemme. Ingen viser kunden, hvad assistenten *ikke* kunne svare på.
- Instantcall vinder på bredde (25+ integrationer, udgående, SIP/API, partnerprogram) og på "menneskelighed". Hejsa vinder på pris og transparens.
- Integrationerne hos alle konkurrenter er *koblinger*: assistenten sender et resumé et sted hen. Ingen dokumenterer, at assistenten *udfører* opgaven i kundens system og bekræfter det over for den, der ringer.

Det efterlader tre huller, som Dialogbot allerede står tættest på at udfylde: resultatbaseret pris, "kun godkendt viden" og egne danske stemmer.

## 2. Positionering i én sætning

**Dialogbot er den danske AI-receptionist, der gør opgaven færdig i jeres systemer – og som I betaler for resultater, ikke minutter.**

Underbudskaber: *"Ingen henvendelse, ingen regning."* · *"Den gætter aldrig – og fortæller jer, hvad den ikke vidste."* · *"Lyder som jer, fra jeres egn."*

## 3. De fem differentiatorer (i prioriteret rækkefølge)

### A. Handlinger, ikke integrationer ("Assistenten gør det færdigt")

Konkurrenterne lister logoer. Dialogbot skal levere et **handlingskatalog**: hver integration eksponerer konkrete handlinger, som assistenten kan udføre *under* samtalen, med bekræftelse tilbage til kunden og et spor i indbakken.

| Branche | Handlinger under samtalen | Systemer (dansk-først) |
|---|---|---|
| Restaurant/takeaway | Opret ordre, bekræft afhentningstid, bordreservation | OnlinePOS, Flatpay, Easytable, DinnerBooking, resOS |
| Håndværker | Opret sag/opgave, book besigtigelse, send SMS-link til fotos, opret kunde i bogføring | Minuba, Ordrestyring.dk, e-conomic, Dinero, Billy |
| Klinik/behandler | Book, flyt, aflys tid; find næste ledige | GeckoBooking, Onlinebooq, EasyPractice, Complimenta, Terapeutbooking |
| Salg/B2B | Opret lead/deal, log opkald, book møde i sælgers kalender | HubSpot, Pipedrive, Google Workspace, Microsoft 365 |
| Alle | Send SMS-bekræftelse, opret kunde, send tilbudsskabelon, udløs webhook | Twilio SMS, Zapier, Make, n8n, webhooks, offentligt API, MCP-server |

Teknisk kerne (bygger videre på det, der findes): `app/modules/integrations/registry.py` udvides fra et *capability*-register til et **connector-/handlingsregister**; handlinger eksponeres som funktionsværktøjer i Vapi (`app/modules/telephony/vapi.py::booking_tools` er mønsteret) og i webchat; pr. arbejdsrum gemmes legitimationsoplysninger krypteret; hver handling logges med input, resultat og hvem der ringede. Den lange hale dækkes af webhooks + Zapier/Make + et offentligt API, og **Dialogbot som MCP-server** gør, at kundens egne AI-værktøjer kan slå op i og handle på Dialogbot-data – det har ingen dansk konkurrent.

API-adgang skal verificeres pr. system, før det loves (OnlinePOS og flere journalsystemer kræver partneraftale). Katalogsiden i produktet viser ærligt tre tilstande pr. system: *klar*, *på vej (dato)*, *via Zapier/webhook*.

### B. Resultatpris med offentlig prisberegner ("Ingen henvendelse, ingen regning")

Model B (149 kr. pr. godkendt henvendelse, 0 kr./md.) og model A (fast pris uden minutloft) findes allerede i koden, men er ikke offentlige. Gør dem til det skarpeste salgsargument:

- Offentlig prisside med **beregner**: kunden indtaster opkald/md. og gennemsnitslængde og ser prisen hos Dialogbot mod "typisk minutpris (1,5–2 kr./min + abonnement)". Vis regnestykket, ikke konkurrentnavne.
- Model A får en synlig **fair-use-grænse** (fx 1.500 min/md., derefter aftale), så marginen er beskyttet (benchmark: break-even ved ca. 1.000–2.300 min/md. med Opus-klasse).
- Samtale-LLM skiftes til Sonnet/Haiku-klasse for telefonopkald; Opus forbeholdes videnimport og daglige rapporter. Det halverer omkostningen pr. minut uden at røre "kun godkendt viden"-garantien.
- Gratis prøve: 30 opkald eller 14 dage uden kort (Hejsa giver 15 min; Online Erhverv 90 dage).

### C. "Lær af opkald" – det synlige læringsloop

"Kun godkendt viden" er i dag en intern arkitekturregel. Gør den til et produkt, kunden kan se hver dag:

- Hver samtale viser, *hvilke godkendte videnpunkter* svaret byggede på.
- Hvert spørgsmål, assistenten ikke kunne svare på, bliver til **et forslag til ny viden** med ét klik til godkendelse (kladde → godkend, samme flow som i `app/modules/knowledge`).
- Overblikket får en boks: "Denne uge kunne assistenten ikke svare på 7 spørgsmål – 5 venter på jer."
- Den daglige rapport (`DailyReport`) får afsnittet "Det lærte assistenten".

Ingen dansk konkurrent viser dette. Det vender transskriptionen fra "log" til "opgaveliste", og det gør assistenten målbart bedre uge for uge, hvilket kunden selv kan se.

### D. "Lyder som jer" – regionale stemmer og egen stemme

De 21 designede regionale stemmer og "egen stemme via browseroptagelse" er unikke i feltet, hvor alle bruger generiske ElevenLabs-stemmer. Sælg det som *identitet* ("vælg en stemme fra jeres egn" · "solo-håndværkeren kan lyde som sig selv"), men lancér først, når lyttetesten består og en rigtig telefontest er gennemført. ElevenLabs forbliver fallback. Røst-v3-licensen skal afklares før kommerciel brug (`docs/voice/rights.md`).

### E. Ærlig EU-linje og AI-oplysning

Instantcalls forside siger "EU-servere", mens deres bilag 3 siger "EU/EØS og/eller USA". Dialogbot skal være den udbyder, der:

- publicerer en **offentlig underdatabehandlerliste** med land pr. leverandør og opdateringsdato,
- tilbyder en **EU-tilstand** (Deepgram EU-endpoint, ElevenLabs EU-residency, LLM via EU-region) som valg pr. arbejdsrum,
- altid oplyser, at der tales med en AI (AI-forordningens art. 50), og dokumenterer samtykkeflowet for kampagner (findes allerede).

## 4. Det, vi ikke konkurrerer på

- **Minutpris.** Den kamp vinder Rigtigt.dk og Hejsa, og den ender på 1 kr./min.
- **"Menneskelignende".** Modsat Instantcall: Dialogbot siger ærligt, at den er en AI, og bruger det som tillidsargument.
- **Antal sprog.** Dansk først; engelsk som nummer to. Ikke "50+ sprog".

## 5. Plan i etaper

Forudsætning (kører parallelt, blokerer ikke etape 0): første rigtige telefonopkald, Stripe-betaling og viderestilling gennemføres mod eksterne leverandører og dokumenteres i `docs/implementation-progress.md`.

| Etape | Indhold | Resultat kunden kan se | Estimat |
|---|---|---|---|
| 0 | Offentlig prisside med beregner; fair-use på model A; Sonnet/Haiku-klasse til samtaler; offentlig underdatabehandlerliste | Priser og databehandling er offentlige | 1 uge |
| 1 | **Handlinger-fundament**: connector-register, krypteret legitimation pr. arbejdsrum, handlingskatalog eksponeret som Vapi- og webchat-værktøjer, handlingslog, side "Integrationer" med ærlig status, tre første connectors: Google/Microsoft-kalender via OAuth (erstatter iCal), webhooks/Zapier/Make, SMS-bekræftelse via Twilio | Assistenten booker i rigtig kalender og sender SMS; alt kan kobles via Zapier | 2–3 uger |
| 2 | **Lær af opkald**: videnreferencer pr. samtale, ubesvarede spørgsmål → kladder, overbliksboks, afsnit i daglig rapport | Kunden ser og godkender ny viden dagligt | 1–2 uger |
| 3 | Connectors bølge 2: e-conomic, Dinero, Billy, HubSpot, Pipedrive, OnlinePOS (efter partneraftale), Minuba/Ordrestyring | Håndværker- og salgsflows kører end-to-end | 3–4 uger |
| 4 | **Branchepakker**: Restaurant, Håndværker, Klinik, Salg som færdige opsætninger (viden-skabelon + handlinger + hilsen + samtaleregler) valgt i guiden | "Kom i gang på 10 minutter" med reelle handlinger | 2 uger |
| 5 | Offentligt API + MCP-server; EU-tilstand pr. arbejdsrum; partnerprogram til bureauer | Platform-position, ikke kun produkt | 3 uger |

## 6. Prompt til Claude Code (masterprompt)

Kopiér hele blokken nedenfor som første besked i en ny Claude Code-session på repoet. Den beder først om en etape-plan i repoets egen stil og går derefter i gang med etape 1.

```text
Du arbejder i repoet dialogbot (dansk AI-receptionist: FastAPI-backend i app/, Next.js-frontend i web/, docs i docs/). Læs først README.md, docs/ADR-001-foundation.md, docs/implementation-progress.md (de nyeste checkpoints), docs/strategy/differentiering-og-handlinger.md og reports/Danske AI telefonassistenter benchmark.md. Følg repoets konventioner: dansk sprog i UI, docs og commit-beskrivelser; ærlig status (intet må vises som "forbundet" eller "aktiv", medmindre det er verificeret – se app/modules/integrations/registry.py); alle arbejdsrumsruter under /workspaces/{workspace_id}/…; version/expected_version på redigerbare indstillinger; Idempotency-Key på effektfulde kommandoer; integrationstests mod rigtig PostgreSQL; ruff; alembic check; docs/openapi.json skal matche koden; nyt checkpoint i docs/implementation-progress.md ved hver leverance.

MÅL: Gør "Handlinger, ikke integrationer" (differentiator A i strategidokumentet) til virkelighed, så assistenten kan udføre opgaver i kundens systemer under en telefonsamtale og i webchatten, med bekræftelse til den der ringer og et spor i indbakken.

TRIN 1 – PLAN (skriv før du koder): Opret docs/strategy/etapeplan-handlinger.md med en etapeplan for etape 1–5 fra strategidokumentets afsnit 5. For hver etape: omfang, datamodel-ændringer, nye endpoints, frontend-sider, tests, risici, og hvad der bevidst IKKE er med. Marker for hvert eksternt system, om API-adgang er offentlig, kræver partneraftale eller er ukendt (verificér mod leverandørens udviklerdokumentation; gæt ikke). Commit planen separat.

TRIN 2 – ETAPE 1, HANDLINGER-FUNDAMENT. Implementér:
1. Connector-register: udvid app/modules/integrations til et register over connectors (fx google_calendar, microsoft_calendar, twilio_sms, webhook, zapier, make) med status pr. arbejdsrum: not_connected | connected | error | not_implemented. Hver connector deklarerer sine handlinger (navn, dansk beskrivelse, JSON-schema for input/output, om den kræver bekræftelse fra kunden i røret).
2. Legitimation pr. arbejdsrum: ny tabel med krypterede tokens (envelope-kryptering med nøgle fra miljøet, aldrig i logs eller API-svar), OAuth-flow for Google Calendar og Microsoft 365 (Graph) med state/PKCE, og API-nøgle/webhook-hemmelighed for webhook-connectoren. Alembic-migration + alembic check.
3. Handlingskatalog eksponeret som funktionsværktøjer: generalisér mønsteret i app/modules/telephony/vapi.py (booking_tools/tool_calls) til en fælles tool-builder, der bruges både af Vapi-assistenten og af webchatten (app/modules/webchat). Kun handlinger fra connectors med status connected medtages. Hvert kald logges i en ny tabel action_runs (workspace, conversation, handling, input, output, status, varighed, fejltekst) og vises i samtalen i indbakken.
4. Tre første connectors med rigtige adaptere bag interface + fake-adapter til test: (a) Google Calendar og Microsoft 365-kalender: find ledige tider, opret, flyt og aflys booking – skal erstatte iCal-koblingen for kunder, der forbinder via OAuth, og falde tilbage til iCal ellers; (b) udgående webhook med HMAC-signatur + Zapier/Make-kompatibelt format (hændelser: ny henvendelse, ny booking, handling udført, samtale afsluttet) med retry via den eksisterende outbox-worker; (c) SMS-bekræftelse via Twilio (den eksisterende platformkonto/underkonto pr. arbejdsrum) som handling "send_sms_bekraeftelse" med skabeloner, der kun kan indeholde godkendt viden og samtaleoplysninger.
5. Frontend: ny side /app/settings/integrationer med katalog (klar / på vej / via Zapier), forbind/afbryd-flow, status og seneste handlinger; handlinger vises i samtalevisningen i indbakken. Følg design-reference/ og eksisterende komponenter.
6. Guiden: nyt valgfrit trin "Forbind jeres systemer" i opsætningsplanen (app/modules/setup), som aldrig blokerer aktivering.
7. Tests: integrationstests for register, kryptering (tokens må aldrig kunne læses via API eller logs), OAuth-state, tool-builder (kun connected connectors eksponeres), action_runs, webhook-signatur og retry, og at fake-adaptere er mærket simulated. Opdater docs/api-contract.md, docs/openapi.json, docs/environment-variables.md og docs/implementation-progress.md (nyt checkpoint med ærlig status: hvad er verificeret mod rigtige leverandører, og hvad er kun testet simuleret).

REGLER: Lov aldrig en integration, som ikke er implementeret – vis den som "på vej" eller "via Zapier". Ingen handling må udføres uden en connected connector og uden at handlingens input er valideret mod schemaet. Betaling eller viden må ikke ændres af handlinger. Skriv små, testede commits på den aktuelle branch og push efter hver leverance. Stop og skriv en klar liste med spørgsmål, hvis noget kræver en beslutning (fx OAuth-klient-id'er, partneraftaler), men færdiggør alt det, der ikke afhænger af svaret.
```

### Opfølgende prompter (én pr. etape)

- **Etape 0:** "Læs docs/strategy/differentiering-og-handlinger.md afsnit 3B og 3E. Byg en offentlig prisside i web/ med beregner (opkald/md. × gns. minutter → pris i model A, model B og 'typisk minutpris 1,5–2 kr./min + abonnement'), indfør fair-use-grænse på model A som konfigurerbar konstant i app/modules/billing, skift samtale-LLM for telefon og webchat til en Sonnet/Haiku-klasse-model via konfiguration (behold Opus til videnimport og rapporter) og publicér en underdatabehandlerliste med land og dato som statisk side. Opdater privatlivspolitikken, så den matcher listen."
- **Etape 2:** "Implementér 'Lær af opkald' (afsnit 3C): gem hvilke godkendte videnpunkter hvert AI-svar byggede på, registrér ubesvarede spørgsmål pr. samtale, generér kladder til ny viden fra dem (samme godkendelsesflow som app/modules/knowledge), tilføj overbliksboks og afsnit i den daglige rapport. Alt skal fungere i både telefon og webchat."
- **Etape 3:** "Byg connectors bølge 2 efter etape 1's register: e-conomic, Dinero, Billy (opret kunde, opret kladde-faktura/tilbud), HubSpot og Pipedrive (opret kontakt/deal, log opkald, book møde), Minuba og Ordrestyring (opret sag). Verificér API-adgang først og markér 'kræver partneraftale' ærligt i kataloget."
- **Etape 4:** "Byg branchepakker (Restaurant, Håndværker, Klinik, Salg) som vælges i guiden: viden-skabeloner som kladder, anbefalede handlinger, hilsen og samtaleregler. Intet aktiveres uden godkendelse."
- **Etape 5:** "Byg et offentligt REST-API med API-nøgler pr. arbejdsrum og en MCP-server, der eksponerer samme handlinger og opslag (viden, henvendelser, bookinger) med samme rettigheder som rollerne i app/core/auth.py. Tilføj EU-tilstand pr. arbejdsrum (Deepgram EU-endpoint, ElevenLabs EU-residency, LLM via EU-region) med ærlig status."
