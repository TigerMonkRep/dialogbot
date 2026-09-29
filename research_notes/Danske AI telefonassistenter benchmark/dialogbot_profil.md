# Dialogbot – produktprofil til benchmark mod danske AI-telefonassistenter

Kilde: git-repositoriet `/home/user/dialogbot` (seneste commit `5d657fd`, "Sales demo calls, consent for every AI call, CVR advertising protection (#29)"; commit-datoer 25.–28. september 2026). Alle kilder nedenfor er filstier i repoet, medmindre andet er angivet. Én webkontrol af dialogbot.dk er foretaget (se sidste afsnit). Læses sammen med `docs/implementation-progress.md`, som er repoets egen statuslog med statusordene "implementeret · testet lokalt/CI · deployet · eksternt verificeret".

**Vigtigste forbehold for hele profilen:** Ifølge repoets egne dokumenter er intet i Dialogbot eksternt verificeret med rigtige leverandørkald (Vapi, Twilio, ElevenLabs, Stripe, Resend, CVR), og der er endnu ikke genereret rigtig dansk tale i den egne TTS-tjeneste ud over to GPU-benchmarks på lejede RunPod-maskiner. Al funktionalitet er testet mod simulerede leverandører (`TELEPHONY_PROVIDER=fake`, `AI_PROVIDER=fake`, `TTS_ENGINE=fake`) — `docs/implementation-progress.md` (checkpoint 25–27), `docs/voice/README.md`, `docs/telephony/README.md`.

---

## 1. Hvilke produkter/services tilbyder Dialogbot?

### Takeaway
Dialogbot er en dansk "AI-reception og kundeopfølgning"-platform for SMV'er med fire produktspor: indgående AI-telefonreception via viderestilling, webchat-widget, booking/kalender og udgående kampagneopkald ("kundeopfølgning"), plus henvendelser (leads), opgaver og daglige rapporter. SMS findes ikke; e-mail bruges kun til konto-/notifikationsmails.

### Cited Findings
- Positionering i sidefoden på forsiden: "Dialogbot • AI-reception og kundeopfølgning". Hero-tekst: "Besvar opkald og chat, hjælp kunder med at booke, og følg op på tilbud — med en AI-assistent, der bruger din virksomheds viden og følger dine regler." — [web/src/app/(public)/page.tsx](web/src/app/(public)/page.tsx)
- **Indgående telefoni (viderestilling):** Kunden beholder sit eget nummer hos sit teleselskab og viderestiller til et Dialogbot-nummer (Twilio-underkonto pr. arbejdsrum, importeret i Vapi). Kunden ser aldrig konti, id'er, nøgler eller webhooks. — [docs/telephony/README.md](docs/telephony/README.md)
- Ved indgående opkald bygger Dialogbot en midlertidig Vapi-assistent med prompt kun fra godkendt viden, hilsen med AI-oplysning; efter opkaldet gemmes transskription som `phone`-samtale, og der oprettes henvendelse + opgave "Ring tilbage", når kunden talte og nummeret kendes. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 11)
- Receptionsmanuskript (navn, du/De, telefonhilsen, hvad der spørges om, eskalering, hvad der ikke må loves, afslutning) indgår i systemprompten for chat og telefon "uden at kunne ændre fakta"; AI-forslag til manuskript. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 21)
- **Webchat-widget:** indlejres med `<script src=".../api/v1/public/webchat/loader.js" data-dialogbot-key="wk_…">`; kører i iframe på API-origin, kun på godkendte domæner; flerturs-svar kun ud fra godkendt viden; udgiftsværn 1.000 tegn/besked, 20 beskeder/samtale, 60 nye samtaler/time/widget, 300 svar/døgn/arbejdsrum (`WEBCHAT_DAILY_REPLY_LIMIT`). — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 8)
- Webchat: "Bliv kontaktet"-knap (navn + e-mail/telefon + samtykke) → henvendelse + opgave med frist +24 t + e-mail til ejere/admins; callback-tidsvinduer ("Hurtigst muligt", formiddag 8–12, eftermiddag 12–16); medarbejder kan overtage chatten fra assistenten ("staff"-mode). — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 9, 12, 14)
- **Booking/kalender:** ledige tider beregnes fra godkendt viden af typen `opening_hours` minus bekræftede bookinger og optaget tid fra kundens kalender; booking via manuel, webchat ("Book en tid") og telefon (Vapi-værktøjer `ledige_tider`/`book_tid`). — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 22)
- **Udgående kampagner:** CSV-import af kontakter, AI-forslag til manuskript, start er en særskilt administratorhandling med lovtjekliste og accept af maksimal pris; worker ringer via Vapi `POST /call` kun i kampagnens tidsrum, ét opkald ad gangen pr. kampagne, nyt forsøg efter 3 timer; udfald AI-vurderet (interesseret/ring tilbage/ikke interesseret/frabeder sig); "ring ikke igen" → permanent spærreliste. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 23)
- Alle kampagnekontakter kræver dokumenteret samtykke (også virksomheder) med henvisning til markedsføringslovens § 10, stk. 1; kontakter uden samtykke springes over. — [docs/sales/demo-calls.md](docs/sales/demo-calls.md), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 27)
- **Leads/henvendelser og opgaver:** tre adskilte akser pr. henvendelse (kvalificering, forløb ny/kontaktet/vundet/tabt, afregning afventer/godkendt/afvist); opgaver med tildeling og frister. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 9)
- **Daglige rapporter** pr. e-mail til ejere/admins (samtaler, AI-svar, tokens, estimeret pris, nye/godkendte henvendelser, opgaver). — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 10)
- **Overblik/notifikationer/hjælp:** KPI-dashboard, notifikationer fra rigtige hændelser, hjælpeside. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 21)
- **Vidensimport fra hjemmeside og CVR:** henter kundens egne sider (maks. 12 sider), AI-udtræk af ydelser/fakta/faste svar som kladder; "priser gemmes aldrig som tal"; CVR-opslag via Erhvervsstyrelsens system-til-system-adgang. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 17–18)
- **SMS:** ikke implementeret. Checkpoint 14: "Ikke implementeret: verifikation af kundens nummer (kræver SMS-udbyder)". Vapi-nummerimport sætter `"smsEnabled": False`. — [docs/implementation-progress.md](docs/implementation-progress.md), [app/modules/telephony/providers.py](app/modules/telephony/providers.py) linje 143
- **Sprog:** Datamodellen har `interface_language`, `default_conversation_language`, `enabled_conversation_languages` (liste, 1–20) og `report_language` ("fire sprogniveauer"); nyt arbejdsrum får `interface_language` = "da" som standard; demo-seed bruger `["da", "en"]` som samtalesprog. Telefonien transskriberer dansk som standard (`deepgram nova-3 language: da`), og ElevenLabs Flash v2.5 låses til `da`. — [app/modules/business/router.py](app/modules/business/router.py) linje 268–279, [app/modules/workspaces/service.py](app/modules/workspaces/service.py) linje 58, [scripts/seed.py](scripts/seed.py) linje 104, [app/modules/telephony/vapi.py](app/modules/telephony/vapi.py) linje 38–40, 194–196
- Egen TTS-tjeneste er "kun dansk" (`language_id="da"`; test: "kun dansk"). — [tts_service/README.md](tts_service/README.md), [docs/voice/testing.md](docs/voice/testing.md)

### Inferences
- Reelt dansk-først produkt: samtalesprog kan konfigureres pr. arbejdsrum, men hele tale-stakken (transskribering, egen TTS, normalisering) er bygget om dansk; andre sprog ville kun kunne køre via ElevenLabs-stemmer og LLM'ens egen flersprogethed, hvilket ikke er dokumenteret som testet.
- "Kundeopfølgning" i markedsføringen = kampagnemodulet (udgående AI-opkald til kundens egen liste med samtykke), ikke klassisk kold telemarketing.

### Gaps
- Ingen dokumentation af, hvilke sprog ud over dansk der er understøttet eller testet i samtale.
- Ingen e-mail-kanal mod slutkunder (kun webchat/telefon); ikke undersøgt om det er planlagt.

---

## 2. Hvilke prismodeller findes, og hvad omfatter de?

### Takeaway
Tre priselementer er kodet som konstanter: Model A fast abonnement 1.495 kr./md. ekskl. moms uden leadgebyr; Model B 149 kr. ekskl. moms pr. godkendt henvendelse (lead) uden abonnement; kampagnepakke 9,00 kr. ekskl. moms pr. kontakt (maks. 2 opkaldsforsøg og 180 sekunders samlet AI-samtaletid). Moms 25 %, afregning via Stripe måned bagud. Der findes ingen minut-, opkalds- eller forbrugspriser og ingen inkluderede minutter.

### Cited Findings
- `MODEL_A_MONTHLY_NET_MINOR = 149_500  # 1.495 kr./md., no lead fee`; `MODEL_B_LEAD_FEE_NET_MINOR = 14_900  # 149 kr. per approved lead`; `TAX_BASIS_POINTS = 2500`; valuta "DKK". "List prices come from the product rules and are not negotiable in the app; choosing a model creates a new immutable version." — [app/modules/billing/agreements.py](app/modules/billing/agreements.py)
- Model A og B er gensidigt udelukkende; "the lead count never changes a model-A total"; "callback is part of reception, never a third price plan". Under model A koster en godkendt henvendelse 0 kr. — [app/modules/billing/money.py](app/modules/billing/money.py), [app/modules/billing/agreements.py](app/modules/billing/agreements.py) (`lead_fee`)
- Kampagner: `PACKAGE_NET_MINOR = 900  # 9,00 kr. excl. VAT per contact`; `MAX_ATTEMPTS = 2`; `MAX_CONNECTED_SECONDS = 180`. "The package is used (billable) when the first attempt is dialled." Prisen snapshot'es pr. kampagne; start kræver accept af maksimal pris (409 hvis prisen er ændret). — [app/modules/campaigns/service.py](app/modules/campaigns/service.py) linje 10–35, [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 23)
- Momsberegning: heltal i øre, 25 %, half-up. Eksempel B: 149 kr. → 14.900 netto / 3.725 moms / 18.625 brutto (øre), dvs. 186,25 kr. inkl. moms. Model A: 1.495 kr. ekskl. = 1.868,75 kr. inkl. moms (samme regel). — [app/modules/billing/money.py](app/modules/billing/money.py), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 9)
- Lead-godkendelse er en idempotent ejer/admin-handling, kræver kvalificeret henvendelse og aftale; prisen låses som snapshot ved godkendelse; afvisning kræver begrundelse. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 9)
- Tvistregler (kun rene funktioner, ingen endpoints): uphold ekskluderer linjen uden kreditnota; reject beholder beløbet til næste faktura. — [app/modules/billing/money.py](app/modules/billing/money.py) (`decide_unbilled_dispute`)
- Fakturering: én faktura pr. arbejdsrum og afsluttet måned (model A-abonnement, model B-godkendte henvendelser, kampagnepakker) med 25 % moms, trukket automatisk via Stripe-kort; "Betaling starter aldrig opkald". Uden `STRIPE_SECRET_KEY` svarer systemet 501. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 24)
- Offentlig prisangivelse på forsiden: "To prismodeller: fast abonnement på 1.495 kr./md. uden leadgebyr, eller 149 kr. pr. godkendt lead. Priser ekskl. moms." — [web/src/app/(public)/page.tsx](web/src/app/(public)/page.tsx) linje 225
- Forsidens FAQ: "Kundeopfølgning i forudbetalte kontaktpakker er planlagt." — [web/src/app/(public)/page.tsx](web/src/app/(public)/page.tsx) linje 22
- `ReceptionAgreement`-dataclassen har felterne `included_chats: int = 0` og `included_ai_minutes: int = 0`, men de bruges ikke i nogen beregning. — [app/modules/billing/money.py](app/modules/billing/money.py)
- Leverandøromkostninger (Vapi-`cost` i USD pr. opkald, nummerkøb) registreres i `telephony_costs`, "er kun interne og indgår aldrig i kundens faktura". Nummerkøbets pris registreres uden beløb (`amount_micros = NULL`). — [docs/telephony/README.md](docs/telephony/README.md), [docs/telephony/owner-setup.md](docs/telephony/owner-setup.md)
- Salgsarbejdsrummets viden skal indeholde "priser (model A og B, kampagnepakker)". — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)
- Hvad model A/B "inkluderer": Aftalen gælder "reception" (telefon + webchat + callback + booking). Der er ingen kode, der begrænser antal opkald, minutter eller samtaler under model A/B; eneste hårde grænser er webchat-udgiftsværn (se afsnit 1) og kampagnepakkens 180 s/2 forsøg. — [app/modules/billing/agreements.py](app/modules/billing/agreements.py), [app/modules/billing/money.py](app/modules/billing/money.py), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 8)

### Inferences
- Dialogbot prissætter *outcome* (godkendte leads) eller flat fee, ikke minutter — det adskiller sig fra minutbaserede konkurrenter. Kunden har under model B intet fast gebyj, men ejer/admin skal aktivt godkende hvert lead, før det faktureres.
- Da leverandøromkostninger (Vapi/Deepgram/LLM/Twilio) ikke videreføres, bærer Dialogbot hele forbrugsrisikoen under model A ved højt opkaldsvolumen.
- Ingen opstartsgebyr, ingen bindingsperiode og ingen tillæg for ekstra numre/brugere er fundet i koden.

### Gaps
- Ingen offentlig prisside (`/pricing`) findes; linket er bevidst udeladt ("Links til sider, der ikke findes (priser, privatliv, vilkår), er udeladt", checkpoint 7). Kravet P05 "Prisberegner" er kun "rene regler", intet endpoint (`docs/requirements-status.md`).
- Ingen dokumentation af, om der findes rabatter, opsigelsesvarsel, bindingsperiode, gratis prøveperiode eller pris for ekstra telefonnumre. Forsiden i Stitch-designet nævner "gratis testkonto", men det er designreference, ikke implementeret tekst (`design-reference/landing/p01_dialogbot_forside_desktop/code.html`).
- Vilkår og handelsbetingelser findes ikke i repoet.

---

## 3. Hvem er målgruppen?

### Takeaway
Danske små og mellemstore virksomheder med travl telefon: eksemplerne er håndværk/gulvfirma, frisør/skønhedsklinik og konsulent/IT-service; sælges til ejer/administrator, der selv godkender viden.

### Cited Findings
- Brancheskifter på forsiden: "Gulvfirma & byggehåndværk", "Frisør & skønhedsklinik", "Konsulent & IT-service". — [web/src/app/(public)/industries.tsx](web/src/app/(public)/industries.tsx)
- Demodata: "Fjord Gulvservice ApS" (håndværk, K04-tilbud ≥ 40 m²) og "Havnebord Café & Catering". — [README.md](README.md)
- Stitch-designreferencen: "Håndværk & Byg", "Frisør & Skønhedsklinik", eksempel "standardprisen for afslibning og 2x lak er 145 kr./m²". — [design-reference/landing/p01_dialogbot_forside_desktop/code.html](design-reference/landing/p01_dialogbot_forside_desktop/code.html)
- Roller: reader/staff/admin/owner; kun ejer kan ændre finansielle aftaler; sidste ejer kan ikke fjernes. — [README.md](README.md)
- Salgsdokument: "Dialogbot sælges bedst ved, at kunden selv hører assistenten." — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)
- dialogbot.dk (webkontrol 29/9 2026): "Targets Danish SMEs across various sectors (construction, salons, consulting, B2B, etc.)". — [https://dialogbot.dk/](https://dialogbot.dk/)

### Inferences
- Ingen enterprise-/callcenter-funktioner (kø, flere agenter, IVR-træer, SLA) er fundet; produktet er designet som SMV-selvbetjening med en "personlig opsætningsplan".

### Gaps
- Ingen dokumenterede kunder, pilotvirksomheder eller referencer i repoet ("148 virksomheder" i Stitch-designet blev bevidst fjernet som usandt — checkpoint 7).

---

## 4. Integrationer

### Takeaway
Integrationslandskabet er smalt og bevidst "ærligt": kalender via hemmelig iCal-adresse (Google/Outlook, ingen OAuth), Stripe til kortbetaling, Resend til e-mail, CVR-registret, Vapi/Twilio/Deepgram/ElevenLabs til tale og Anthropic til LLM. Der findes ingen CRM-, e-conomic-, Zapier- eller udgående webhook-integration.

### Cited Findings
- Kapabilitetsregistret opregner præcis: `email` (Resend/simuleret), `telephony.inbound`, `telephony.outbound`, `voice.dialogbot` (egen TTS), `calendar`, `payment` (Stripe), `ai.assistant_preview`, `ai.conversation`, `knowledge.source_import`, `cvr.lookup`, `webchat`. "Anything not implemented in this stage is reported as `not_implemented` and can never be reported as connected or as a passed test." — [app/modules/integrations/registry.py](app/modules/integrations/registry.py)
- Kalender: "Kalender uden OAuth-app: ejerens hemmelige iCal-adresse (Google/Outlook) læses hvert 15. min i workeren ... bookingerne udgives som et hemmeligt iCal-feed `/api/v1/public/calendar/{token}.ics`". "Ikke eksternt verificeret: Google/Outlooks opdateringsinterval for abonnerede kalendere (typisk 8–24 timer hos Google)". — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 22)
- Indgående webhooks, der findes: `/api/v1/webhooks/resend`, `/api/v1/webhooks/stripe`, `/api/v1/webhooks/vapi`. — [app/modules/webhooks/router.py](app/modules/webhooks/router.py), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 11)
- Ingen forekomster af "e-conomic", "HubSpot", "Pipedrive", "Zapier" eller "CRM" i `app/`, `docs/` eller `web/src` (ripgrep 29/9 2026). — repo-søgning
- Stitch-designet lover "synkroniser direkte til jeres forretningssystemer" og "SMS-bekræftelse", men den implementerede forside udelader disse påstande; checkpoint 7 opregner de bevidst fjernede påstande. — [design-reference/landing/p01_dialogbot_forside_desktop/code.html](design-reference/landing/p01_dialogbot_forside_desktop/code.html), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 7)
- Offentligt API: REST under `/api/v1` med OpenAPI (`docs/openapi.json`), Bearer-sessionstokens, idempotensnøgler; dokumenteret Python-referenceklient. — [README.md](README.md), [docs/api-contract.md](docs/api-contract.md)
- CVR: `GET /workspaces/{id}/cvr/{cvr}` mod Erhvervsstyrelsens system-til-system-adgang (basic auth, gratis adgang); "Ikke eksternt verificeret". — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 18), [app/config.py](app/config.py) linje 89–91

### Inferences
- Konkurrenter med CRM/regnskabsintegrationer (e-conomic, Dinero, HubSpot) står stærkere på integrationsdimensionen; Dialogbots svar er iCal-feed + eget REST-API.

### Gaps
- Om REST-API'et er tænkt som kundevendt integrations-API (API-nøgler for kunder) fremgår ikke; kun sessionstokens er dokumenteret.

---

## 5. Teknologiplatform og omkostninger pr. minut

### Takeaway
Stakken er FastAPI/PostgreSQL (Supabase, eu-central-1) på Render (Frankfurt) + Next.js på Vercel; telefoni er Twilio-underkonti orkestreret gennem Vapi med Deepgram Nova-3 (dansk) STT; LLM-standard er Anthropic `claude-opus-5`; stemme er ElevenLabs i dag og egen Røst-v3/Chatterbox-TTS på GPU (Hetzner/RunPod) som mål. Egen TTS er dokumenteret som *dyrere* end ElevenLabs under ca. 5.000 samtaleminutter/md.

### Cited Findings
- Backend: Python 3.12, FastAPI 0.141, SQLAlchemy 2.1, Alembic, PostgreSQL 16, psycopg 3, argon2, structlog; frontend Next.js 16 + TypeScript + Tailwind 4 med BFF og httpOnly-cookie. — [README.md](README.md)
- Hosting: "Render til API og worker, Vercel til Next.js, Supabase til PostgreSQL/Storage"; eget schema `dialogbot`, RLS ikke indført. Render region `frankfurt`, plan `starter`, 2 uvicorn-workers. Supabase-projekt `dialogbot-staging`, eu-central-1, "10 USD/md. bekræftet af bruger". — [docs/ADR-002-hosting-and-services.md](docs/ADR-002-hosting-and-services.md), [infra/render.yaml](infra/render.yaml), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 2)
- LLM: `AI_PROVIDER` (`none`/`anthropic`/`fake`), `AI_MODEL_ID` standard `claude-opus-5`; officiel SDK `anthropic==1.8.0`, prompt caching, server-side fallbacks; refusals maskeres på dansk. Vapi-assistenten bruger `VAPI_MODEL_PROVIDER` standard `anthropic` og `VAPI_MODEL` standard = `AI_MODEL_ID`. — [app/config.py](app/config.py) linje 51–52, 81–82, [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 6), [app/modules/telephony/vapi.py](app/modules/telephony/vapi.py) linje 212
- STT: `DEFAULT_TRANSCRIBER = {"provider": "deepgram", "model": "nova-3", "language": "da"}`. — [app/modules/telephony/vapi.py](app/modules/telephony/vapi.py) linje 38
- Stemme i dag: ElevenLabs (`11labs`) Multilingual v2 / Flash v2.5 (sprog låst `da`) / Turbo v2.5 pr. nummer; "Hør stemmen"-preview via ElevenLabs TTS-API. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 15–16), [app/modules/telephony/vapi.py](app/modules/telephony/vapi.py) linje 97, 194
- Telefoni-arkitektur: Twilio-hovedkonto ejes af Dialogbot; Twilio-underkonto + dansk nummer pr. arbejdsrum; nummer importeres i Vapi med webhook + Bearer; kundens eget nummer viderestilles. — [docs/telephony/README.md](docs/telephony/README.md)
- Egen TTS: separat container (`tts_service/`, CUDA 12.4), motor Chatterbox Multilingual (MIT-kode) med vægte **Røst-v3** (`CoRal-project/roest-v3-chatterbox-500m`, Alexandra Instituttet, finetunet på >2.000 timers dansk tale) ved fastlåst commit `7ce205ce…`; API'et indlæser aldri en model. Vapi kaldes med `custom-voice` og ElevenLabs som `fallbackPlan`. — [tts_service/README.md](tts_service/README.md), [docs/voice/ADR-003-voice-library.md](docs/voice/ADR-003-voice-library.md), [docs/voice/rights.md](docs/voice/rights.md)
- GPU-krav: "NVIDIA-GPU med ≥ 16 GB VRAM. Chatterbox bruger ca. 5–7 GB"; region EU (Tyskland/Finland); Render har ingen GPU'er; kandidater Hetzner GEX44 eller RunPod Secure Cloud L4. — [docs/voice/operations.md](docs/voice/operations.md)
- **Priskilder (fundet 27/9 2026, "skal bekræftes"):** Hetzner GEX44 €184/md. + €79 opsætning; RunPod L4 $0,49/time; Modal L4/A10G ≈ $0,80/$1,10 pr. time; **Vapi platform $0,05/min + udbydernes kostpris**; **Deepgram Nova-3 $0,0058/min (multilingual)**; **ElevenLabs via Vapi ca. $0,04/min**; Supabase Storage $0,021/GB/md. — [docs/voice/costs.md](docs/voice/costs.md)
- Antagelse: "Assistenten taler ca. 40 % af samtaletiden. 1 samtaleminut giver ca. 0,4 genererede lydminutter." — [docs/voice/costs.md](docs/voice/costs.md)
- **Pilotscenarie A:** 1 × Hetzner GEX44 varm hele tiden €184/md. fast (1–2 samtidige samtaler antaget); Vapi $0,05 × minutter; Deepgram ≈ $0,006 × minutter; LLM "afhænger af model og længde"; telefoni "ikke prissat. Dansk nummer er endnu ikke købt." — [docs/voice/costs.md](docs/voice/costs.md)
- **Eksempel 1.000 samtaleminutter/md.:** "Egen TTS koster €184 fast. ElevenLabs ville koste ≈ $40 (1.000 × $0,04). Ved lav volumen er egen stemme altså **dyrere**. Den er begrundet i kontrol, egne danske stemmer og dialekter, ikke i pris. Break-even er ved ca. 5.000 samtaleminutter pr. måned, hvis antagelserne holder." — [docs/voice/costs.md](docs/voice/costs.md)
- Alternativ kun i åbningstid: Modal L4 hverdage 8–18 ≈ $176/md., koldstart på minutter udenfor → reservestemme. — [docs/voice/costs.md](docs/voice/costs.md)
- **Skalering:** "20 samtidige samtaler: ≈ 10–20 × GEX44 (€1.840–3.680/md.) eller RunPod L4 døgnet rundt (≈ $358/md. pr. replika)"; "Chatterbox kører i dag én ad gangen pr. instans." — [docs/voice/costs.md](docs/voice/costs.md)
- **Målt latens (28/9 2026, rigtig syntese):** RunPod L4 uden streaming: syntese pr. enhed p50 2.932 ms / p95 3.952 ms, RTF 0,83–0,94 → "L4 opfylder ikke målet om p95 < 1,5 s". RunPod RTX 4090 ($0,74/t) med streaming: første lyd på serveren p50 652 ms / p95 661 ms, RTF 0,60–0,90, 110/110 sætninger under 1,5 s; 2 samtidige: første lyd p95 1,34 s med huller op til 0,43 s; 4 samtidige: p95 8,6 s. "Én RTX 4090 klarer altså 1 samtale uden huller og 2 med små huller." Samlede GPU-omkostninger til målingerne: ca. $0,16 + $1,05. — [docs/voice/testing.md](docs/voice/testing.md), [docs/voice/evidence/](docs/voice/evidence/)
- Finetuning: ikke planlagt; et forsøg anslås til "$20–60 i GPU-tid" på A100. — [docs/voice/costs.md](docs/voice/costs.md)
- Anthropic-omkostning logges pr. kald i `ai_usage` som estimeret pris i µUSD "kun for kendte modeller"; ingen DKK-sats pr. samtaleminut for LLM er dokumenteret. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 6)
- Vapi-opkaldsomkostning (`cost` i USD) gemmes pr. opkald i `telephony_costs`. — [docs/telephony/README.md](docs/telephony/README.md)

### Inferences
- **Variabel platformomkostning pr. samtaleminut med ElevenLabs-stak (uden LLM og Twilio-minutter), beregnet ud fra costs.md-satserne:** Vapi $0,05 + Deepgram ≈ $0,006 + ElevenLabs ≈ $0,04 ≈ **$0,096/min** (~0,65 kr./min ved ~6,8 kr./USD — kursantagelse, ikke fra repoet). Ved 1.000 min/md. ≈ $96 + LLM + telefoni.
- **Med egen TTS på Hetzner GEX44:** €184/md. fast ⇒ ved 1.000 min ≈ €0,18/min for TTS alene (ca. 4,5× ElevenLabs); ved 5.000 min ≈ €0,037/min (paritet). Kapacitetsloftet på 1–2 samtidige samtaler pr. GPU gør dog, at 5.000 min/md. kræver flere GPU'er ved spidsbelastning — break-even-tallet i costs.md er derfor optimistisk (egen vurdering).
- Model A på 1.495 kr./md. (~$220) dækker ifølge satserne omtrent 1.500–2.000 samtaleminutter i rene platformomkostninger (uden LLM og Twilio) — dvs. Dialogbot har negativ bruttomargin på model A ved kunder over ca. 30–40 minutters AI-telefoni om dagen, hvis LLM-omkostningerne til `claude-opus-5` er væsentlige (egen beregning; LLM-pris ikke i repoet).

### Gaps
- Ingen LLM-pris pr. minut/samtale i repoet; ingen Twilio-nummer- eller minutpris ("prisen vises før køb").
- Ingen samlet "kostpris pr. samtaleminut" er beregnet i repoet — kun delsatser.
- Ingen dokumentation af LLM-latens eller end-to-end svartid i et rigtigt opkald.

---

## 6. Danske sprog- og stemmedifferentiatorer

### Takeaway
Dialogbots tydeligste differentiator er et eget dansk stemmebibliotek: 21 "designede" regionale stemmer (blandet af flere NST-oplæsere, så ingen enkeltperson efterlignes), kunders egen stemme via browseroptagelse med samtykke, dansk tal-/dato-/beløbsnormalisering og pinning af stemmeversion pr. opkald. Intet er dog produktionsgodkendt: ingen lyttetest med ≥ 3 lyttere, ingen rigtig telefontest, og rettigheder/licens (Røst-v3 RAIL-licens) afventer jurist.

### Cited Findings
- Designede stemmer: "En designet stemme er en dansk stemme, der ikke tilhører en bestemt person. Den er blandet af flere rigtige oplæsere fra samme gruppe (køn, alder og region) i NST-korpusset (`alexandrainst/nst-da`, CC0-1.0)"; lighedskontrol: må ikke ligne én oplæser mere end to rigtige oplæsere ligner hinanden (+0,03) og aldrig over 0,90. — [docs/voice/designed-voices.md](docs/voice/designed-voices.md)
- Katalog v1 (27/9 2026): "21 af 22 stemmer bestod lighedskontrollen"; regioner: Fyn, Jylland, Nord-/Øst-/Vest-/Sønderjylland, Storkøbenhavn, Vest- og Sydsjælland, Øerne; aldersgrupper 18–34, 35–54, 55+; mand/kvinde. "Dialekten er ikke lyttevurderet." Ejeren har lyttet til alle 21 og godkendt ("allesammen er gode") — "Det tæller som én lytter." — [docs/voice/designed-voices.md](docs/voice/designed-voices.md)
- Egen stemme: kunden indtaler i browseren (`/app/voices/own`) med samtykketekst, kort manus (15 sætninger, ca. 2 min) eller standard (400 sætninger, 25–30 min) med firmanavn/ydelse/by flettet ind; kvalitetstjek pr. sætning; privat stemme kun i eget arbejdsrum; tilbagetrækning sletter optagelser straks. Målt lighed 0,82 i en test; "Samtykketeksten er ikke gennemgået af en jurist." — [docs/voice/own-voice.md](docs/voice/own-voice.md)
- Dansk normalisering: tal, beløb, datoer, klokkeslæt, telefonnumre i par og e-mail staves ud; versioneret udtaleordbog; testet med 4.100 tal round-trip og 110-sætnings testsæt. — [docs/voice/ADR-003-voice-library.md](docs/voice/ADR-003-voice-library.md), [docs/voice/testing.md](docs/voice/testing.md)
- Telefonprompt `phone-v2`: "naturligt dansk talesprog, korte sætninger, du-form, danske vendinger, tal/beløb/klokkeslæt som de siges, ét spørgsmål ad gangen". — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 15)
- Publiceringskontroller, der ikke kan forfalskes i kode: `rights`, `normalization`, `synthesis_smoke` (rigtig motor), `listening_test` (≥ 3 lyttere, gennemsnit ≥ 4), `telephony_test` (opkalds-ID). Platformstemmer kræver alle fem. — [docs/voice/ADR-003-voice-library.md](docs/voice/ADR-003-voice-library.md)
- Pinning pr. samtale: "en opdatering eller rollback aldrig skifter stemme midt i et opkald"; suspendering → 503 → Vapi bruger ElevenLabs-reservestemme. — [docs/voice/ADR-003-voice-library.md](docs/voice/ADR-003-voice-library.md)
- Status: "Der er endnu ikke genereret rigtig dansk tale" (i udviklingsmiljøet; huggingface.co blokeret, ingen GPU); "Stemmemodulet er **ikke klar til produktion**." Efterfølgende GPU-benchmarks på RunPod (28/9) brugte "modellens egen indbyggede `conds.pt`, ikke en CoRal-TTS-kandidat"; lydkvalitet "ikke vurderet". — [docs/voice/README.md](docs/voice/README.md), [docs/voice/testing.md](docs/voice/testing.md)
- Rettigheder: Røst-v3 under Alexandra Instituttets RAIL-baserede licens "Kræver juridisk gennemgang"; brugsbegrænsning 4(c) (autonom interaktion kræver oplysning og samtykke), 3(b) (fuldautomatiske bindende beslutninger, fx bookinger) og 4(b) (efterligning af stemme) skal vurderes af jurist; kundevilkår skal videreføre begrænsningerne. Chatterbox Multilingual V3 basismodel "Lød ikke tilfredsstillende på dansk". — [docs/voice/rights.md](docs/voice/rights.md)
- Plan om udvidelse "mod 16 stemmer: indkøb af indtalere med aftaler" (`recording-brief.md`); "Ingen aftaler findes." — [docs/voice/README.md](docs/voice/README.md), [docs/voice/rights.md](docs/voice/rights.md)
- Stitch-designets påstande "Latency < 280 ms", "100 % dansk hosting", "Neural-DK" er bevidst udeladt af den rigtige forside som usande. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 7)
- Øvrige stated differentiators på forsiden: "Du bestemmer, hvad Dialogbot må sige og gøre"; "Åbningstider, priser og tilbud gælder præcis som godkendt – kladder bruges aldrig"; "Den gætter ikke"; "Det virker også uden hjemmeside – ingen webcrawler, der gætter forkert"; "Se, hvem der henvendte sig ... uden at lytte optagelser igennem". — [web/src/app/(public)/page.tsx](web/src/app/(public)/page.tsx)

### Inferences
- Mod konkurrenter på ElevenLabs har Dialogbot potentielt (a) regionale danske stemmer uden persontilknytning, (b) kundens egen stemme uden ElevenLabs-cloning-vilkår, (c) EU-hostet syntese — men i dag kører telefonen fortsat på ElevenLabs, så differentiatoren er ikke leveret.
- "Kun godkendt viden"-arkitekturen (kladde → godkend → assistent) er den mest modne differentiator og gennemsyrer hele kodebasen.

### Gaps
- Ingen lyttetest, MOS-score eller kvalitativ vurdering af dansk udtalekvalitet foreligger.
- Uafklaret om Røst-v3-licensen overhovedet tillader kommerciel autonom telefoni uden yderligere samtykke.

---

## 7. GDPR og datahåndtering

### Takeaway
Dataansvarlig er Dialogbot, Abildgade 18, 8200 Aarhus; database og API er i EU (Supabase eu-central-1, Render Frankfurt), men privatlivssiden oplyser selv, at tale-/AI-leverandørerne Vapi, Twilio, Deepgram, ElevenLabs og Anthropic "kan behandle data i USA". Sikkerhedsdesignet er gennemgående (hash-lagrede tokens, arbejdsrumsisolation, auditlog), men der er ingen DPA'er, RLS eller dokumenteret sletningspolitik for samtaledata.

### Cited Findings
- `/privatliv`: dataansvarlig "Dialogbot, Abildgade 18, 8200 Aarhus, Danmark"; venteliste: opbevaring "højst 24 måneder"; "Oplysningerne ligger i vores database hos Supabase og behandles af vores server hos Render (Frankfurt, EU). Websiden leveres via Vercel. De fungerer som databehandlere." — [web/src/app/privatliv/page.tsx](web/src/app/privatliv/page.tsx)
- Demo-opkald: "Opkaldet går gennem vores telefoni- og taleleverandører Vapi, Twilio, Deepgram og ElevenLabs samt AI-modellen hos Anthropic. De er databehandlere og kan behandle data i USA." Udskrift af samtalen gemmes; slettes på anmodning. Klageadgang til Datatilsynet. — [web/src/app/privatliv/page.tsx](web/src/app/privatliv/page.tsx)
- AI-oplysning: telefonhilsen "får altid AI-oplysning"; kampagnens første replik "får altid AI-oplysning"; AI-oplysning i webchat-vinduet. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 8, 21, 23)
- Samtaledata: transskription gemmes som `phone`-samtale (system-/tool-beskeder udeladt). Ingen optagelser (audio) af kundesamtaler er nævnt som gemt; "Kun standardprøver caches; egne tekster og samtaletekster caches eller logges aldrig" (TTS). — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 11), [docs/voice/ADR-003-voice-library.md](docs/voice/ADR-003-voice-library.md)
- Sikkerhed: tokens kun som SHA-256; opake sessionstokens; arbejdsrumsisolation testet (A kan ikke se B, 404); auditlog; webhook-signaturer (Svix/Stripe HMAC/Vapi Bearer i konstanttid); SSRF-sikring på hjemmesideimport og iCal; kortdata "rører aldrig vores servere" (Stripe Checkout). — [README.md](README.md), [docs/final-report.md](docs/final-report.md), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 17, 22, 24)
- "RLS er ikke indført ... adskillelsen ligger i applikationslaget (testet)". — [docs/ADR-002-hosting-and-services.md](docs/ADR-002-hosting-and-services.md)
- Fonte self-hostes "ingen runtime-kald til Google (også GDPR-venligere)". — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 3)
- Stemmedata: privat Supabase-bucket `voice-private`, kun server-side adgang; egen-stemme-samtykke registreres som rettighedspost; tilbagetrækning sletter straks. — [docs/voice/operations.md](docs/voice/operations.md), [docs/voice/own-voice.md](docs/voice/own-voice.md)
- Retsgrundlag for udgående AI-opkald: samtykke, markedsføringslovens § 10, stk. 1; "Den juridiske vurdering er ikke gennemgået af en advokat." — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)
- Ventelistedata kan eksporteres/slettes via `python -m scripts.waitlist export|delete <e-mail>`. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 7)

### Inferences
- Sammenlignet med konkurrenter, der markedsfører "100 % dansk/EU-hosting", er Dialogbots reelle position "EU-database, US-databehandlere for tale og LLM" — samme mønster som de fleste Vapi/ElevenLabs-baserede konkurrenter. Egen TTS i EU ville flytte stemmedelen, men ikke STT (Deepgram) eller LLM (Anthropic).

### Gaps
- Ingen databehandleraftaler, ingen fortegnelse, ingen sletningsfrister for samtaler/transskriptioner/leads, ingen privatlivspolitik for selve app-brugen (kun venteliste + demo-opkald) i repoet.
- Ingen dokumentation af, om Vapi/Twilio optager lyd, og hvor længe.

---

## 8. Onboardingflow

### Takeaway
Selvbetjent, serverberegnet "personlig opsætningsplan" med én næste handling ad gangen: konto → e-mailbekræftelse → arbejdsrum → virksomhedsprofil (manuelt eller fra hjemmeside/CVR) → mål/sprog → viden som kladder → godkendelse → tjek → telefoni i fem trin (nummerbekræftelse med kontrolopkald, provisionering, viderestillingsguide med GSM-koder, prøveopkald, aktivering).

### Cited Findings
- Etape 1-omfang: "konto → e-mailbekræftelse → arbejdsrum → virksomhedsprofil/kategorier → mål/sprog → manuel viden → godkendelse → personlig opsætningsplan med tjek → invitation af kolleger → gem/genoptag". — [README.md](README.md)
- Opsætningsplan G01–G08: "serverberegnet plan med nødvendige/valgfrie trin, afhængigheder, rettighedsblokering, `not_available` for ikke-implementerede kapabiliteter, ærlig procent, næste handling, gem/genoptag, tildeling". — [docs/final-report.md](docs/final-report.md)
- Vidensgodkendelse: "versionerede emner (kladde → gennemgang → godkendt → superseded), kun én åben kladde og ét godkendt pr. emne (databasegaranteret), assistent-endpoint med udelukkende godkendt viden". Sletning af godkendt viden øger vidensrevisionen, "så assistenten straks holder op med at bruge den". — [docs/final-report.md](docs/final-report.md), [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 20)
- AI-assistance i opsætning: forslag til mål/kanaler, receptionsmanuskript, kampagnemanuskript; hjemmeside læses automatisk første gang. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 19, 21, 23)
- Telefoni, fem trin: (1) nuværende nummer + kontrolopkald med 6-cifret kode (10 min, maks. 5 forsøg, 3 opkald/time); danske lokalnumre kræver CVR-udskrift (Twilio-krav); (2) "Forbind telefonen" → provisioneringsjob (underkonto, nummerkøb, Vapi-import) → viderestillingsguide pr. abonnementstype (mobil: GSM-koder `**61*`, `**67*`, `**62*`, `**21*`, `##002#`); (3) "Sådan skal vi svare"; (4) prøveopkald (15 min, mindst 3 s, skal ende i indbakken); (5) aktivér — kun efter bestået prøveopkald og valgt prisaftale. — [docs/telephony/README.md](docs/telephony/README.md)
- Twilio-bundles (regulatorisk dokumentation for danske numre) godkendes manuelt af operatør; "Den første uge kan det være manuelt." Alternativ: danske mobilnumre kræver kun oplysninger. — [docs/telephony/owner-setup.md](docs/telephony/owner-setup.md)
- Webchat aktiveres kun "når AI, godkendt viden og domæner er på plads"; tjek kræver at chatvinduet er åbnet på et godkendt domæne inden for 30 dage. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 8)
- Forsiden: "Opret en konto, beskriv virksomheden og læg ydelser, priser og åbningstider ind. En personlig plan viser én næste handling ad gangen – også uden hjemmeside." — [web/src/app/(public)/page.tsx](web/src/app/(public)/page.tsx)
- Adgang i dag: forsiden er bag en preview-gate (P00) med forhåndskode + venteliste; "Privat preview"-banner. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 7)

### Inferences
- Time-to-live er struktureret men ikke "5 minutter": nummerdokumentation, Twilio-bundle-godkendelse og operatørens manuelle trin ligger imellem. Konkurrenter, der leverer et nummer med det samme, vil være hurtigere i onboarding.

### Gaps
- Ingen målt onboarding-tid; ingen rigtig kunde har gennemført flowet ("Rigtig viderestilling og rigtigt indgående opkald: Ikke udført").

---

## 9. Operatør- og salgsfunktioner

### Takeaway
Dialogbot har et internt operatørlag (`/app/operator/*`, rolle `is_platform_operator`) til telefoni-provisionering, stemmegodkendelse og et sælgerflow, samt tre lovlige demo-veje: demonummer, "Ring mig op nu" på forsiden med samtykke, og sælgerinitieret AI-opkald efter mundtligt ja — alle kørt fra et eget "salgsarbejdsrum".

### Cited Findings
- Tre demo-veje med samtykkegrundlag (demonummer: kunden ringer selv; "Ring mig op nu": flueben, version `demo-call-web-v1`; sælgerflow `/app/operator/sales`: sælgerens bekræftelse, `demo-call-seller-v1`, auditeret). Opkaldet varer højst 5 minutter; assistenten "tilbyder at være receptionist for kundens egen virksomhed i et rollespil". — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)
- Forsidetekst: "Skriv dit nummer og din virksomhed. Assistenten ringer inden for et halvt minut og lader som om, den er receptionist hos jer." — [web/src/app/(public)/demo-call.tsx](web/src/app/(public)/demo-call.tsx)
- Begrænsninger: kun danske numre (ikke 90-numre), ét opkald pr. nummer pr. døgn, standard 20 opkald/time, 08:00–20:00 dansk tid, honeypot; spærreliste afsløres ikke. Sælgerflowet afviser reklamebeskyttede virksomheder ved CVR-adgang. — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)
- Efter opkald: rapport klassificeres som kampagne → henvendelse (kilde `demo_call`) + opgave med frist 2 timer i salgsarbejdsrummet. — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)
- Operatør-telefoni: se job/trin/fejl, bekræfte nummer manuelt, godkende dokument med Twilio-bundle-SID, køre job nu, tilknytte eksisterende nummer (migrering), give afsendertilladelse; alt auditeres. — [docs/telephony/README.md](docs/telephony/README.md)
- Operatør-stemmer: rettighedsposter, versioner, kontroller, godkend/aktivér/rollback/suspendér (`/app/operator/voices`). — [docs/voice/README.md](docs/voice/README.md)
- Status: "Implementeret og testet med simuleret Vapi"; "Ikke eksternt verificeret: et rigtigt demo-opkald og CVR-feltet `Vrvirksomhed.reklamebeskyttet`". — [docs/sales/demo-calls.md](docs/sales/demo-calls.md)

### Inferences
- "Prøv selv-opkald fra forsiden" er en salgsmekanik, flere konkurrenter også bruger; Dialogbots version er usædvanlig eksplicit om § 10-samtykke.

### Gaps
- Ingen partner-/forhandlerprogram, white-label eller multi-tenant-agentur-funktioner fundet.

---

## 10. Implementeringsstatus og modenhed

### Takeaway
Repoet er 4 dage gammelt (25.–28. sep. 2026) med 27 checkpoints; ca. 143 backend-tests og 48 E2E-tests er grønne mod simulerede leverandører, staging findes på Render/Vercel/Supabase, men **ingen rigtig telefonsamtale, AI-opkald, betaling eller e-mail er gennemført mod en ekstern leverandør**, og forsidens FAQ er efter kodens seneste udvikling delvist forældet.

### Cited Findings
- README-status: "etape 1 implementeret og testet lokalt/CI; milepæl A (frontend + driftskonfiguration) i gang ... Ikke deployet, ikke browserafprøvet." (README er ikke opdateret efter checkpoint 2.) — [README.md](README.md)
- Git-historik: første commit-dato 25. sep. 2026, seneste 28. sep. 2026 (PR #29). — `git log` i repoet
- Staging eksternt verificeret: GitHub-repo `TigerMonkRep/dialogbot`, CI grøn, Supabase `dialogbot-staging` eu-central-1, Render `dialogbot-api-staging` live (checkpoint 2–3). Staging kører `AI_PROVIDER=none`/`EMAIL_ADAPTER=simulated` ved checkpoint 5–6. — [docs/implementation-progress.md](docs/implementation-progress.md)
- Tests: 142 backend-tests bestået pr. 27/9 (`pytest`), 7 TTS/pipeline-tests, E2E-suite 48 bestået (24 rejser × 2 viewports). Repoet indeholder 28 testfiler med 143 `def test_` (optalt 29/9). — [docs/voice/testing.md](docs/voice/testing.md), `tests/`
- **Ikke eksternt verificeret (eksplicit pr. checkpoint):** Resend (5), Anthropic-nøgle/`claude-opus-5` (6), webchat på rigtig hjemmeside (8), Vapi-konto/nummer (11), lydkvalitet/latens/Vapi-accept af `nova-3`+`da` (15), ElevenLabs-kald (16), hjemmesideudtræk med rigtig model (17), CVR-registret (18), Google/Outlook-kalender (22), rigtigt udgående opkald (23), rigtige Stripe-kald (24), rigtig dansk syntese/lyttetest (25), rigtige Twilio-/Vapi-kald, viderestilling, indgående opkald (26), rigtigt demo-opkald (27). — [docs/implementation-progress.md](docs/implementation-progress.md)
- Stemmemodul: "ikke klar til produktion"; egen TTS kun benchmarket på lejede RunPod-GPU'er; telefonen bruger ElevenLabs indtil en stemme er godkendt og `TTS_ENGINE=http` er sat. — [docs/voice/README.md](docs/voice/README.md)
- Ikke implementeret (telefoni): automatisk Twilio-bundle via Regulatory API, nummerflytning/porting, frigivelse af numre, prisimport fra Twilio. — [docs/telephony/owner-setup.md](docs/telephony/owner-setup.md)
- Ikke implementeret (øvrigt): SMS-verifikation, automatisk opkald i callback-vindue (checkpoint 14); dokumentupload til viden (17); tvister/kreditnotaer (13); operatørgrants M02, RLS (final-report). — [docs/implementation-progress.md](docs/implementation-progress.md), [docs/final-report.md](docs/final-report.md)
- Kravstatus (etape 1-dokument, ikke opdateret siden): O05 assistentmanuskript "Ikke implementeret", O06 simulerede testscenarier "Ikke implementeret", G06 aktivering "501". Senere checkpoints (21–26) har implementeret manuskript og aktivering, så dokumentet er forældet på de punkter. — [docs/requirements-status.md](docs/requirements-status.md) vs. [docs/implementation-progress.md](docs/implementation-progress.md)
- Forsidens FAQ siger stadig "Telefoni er under udvikling og kan ikke tilkobles endnu" og "Kalenderforbindelse til Google og Microsoft er planlagt", og banner: "Telefoni, webchat, kalender og kampagner er under udvikling" — skrevet ved checkpoint 7, før checkpoint 22–26 implementerede kalender og telefoni (simuleret). — [web/src/app/(public)/page.tsx](web/src/app/(public)/page.tsx) linje 18–19, 52
- Juridisk: markedsføringslov-vurdering, samtykketekster, Røst-v3-licens og egen-stemme-samtykke er alle "ikke gennemgået af en advokat/jurist". — [docs/sales/demo-calls.md](docs/sales/demo-calls.md), [docs/voice/rights.md](docs/voice/rights.md), [docs/voice/own-voice.md](docs/voice/own-voice.md)
- Kodebasen er bygget med gennemgående "ærlighed"-princip: kapabiliteter kan aldrig vise "connected" uden reel konfiguration; simulerede tests kan ikke aktivere produktion. — [app/modules/integrations/registry.py](app/modules/integrations/registry.py), [docs/final-report.md](docs/final-report.md)

### Inferences
- Modenhedsniveau i benchmark-termer: **pre-launch / privat preview**. Arkitektur og testdækning er høj for alderen, men produktet har ikke håndteret et eneste rigtigt kundeopkald ifølge dokumentationen. Konkurrenter i drift har derfor et reelt forspring på "bevist i produktion".
- Repoet ser ud til at være udviklet primært af en AI-agent i tæt løb (checkpoint-format med "Bruger:"/"Claude:"-handlinger) — relevant for at vurdere vedligeholdelsesrisiko, men ikke dokumenteret som fakta ud over checkpoint-teksterne.

### Gaps
- Ingen produktionsmiljø, ingen oppetids-/SLA-dokumentation, ingen supportorganisation beskrevet.
- Ingen dato for offentlig lancering ("Q2 åbning" i Stitch-designet blev fjernet som usandt).

---

## 11. Offentlig website (webkontrol)

### Takeaway
dialogbot.dk er en privat preview-/ventelisteside uden priser.

### Cited Findings
- WebFetch af https://dialogbot.dk/ (29/9 2026): "private preview/waitlist page, not a live public website ... closed beta"; produktet beskrives som "en dansk AI-assistent, der skal tage telefonen, besvare webchat og følge op på tilbud for travle virksomheder"; tre områder Telefoni / Opfølgning / Kontrol; "No pricing information is disclosed on this page"; invitationskoder kræves. — [https://dialogbot.dk/](https://dialogbot.dk/)
- Dette stemmer med repoets P00-preview-gate og venteliste. — [docs/implementation-progress.md](docs/implementation-progress.md) (checkpoint 7)

### Inferences
- Prisen 1.495 kr./md. / 149 kr. pr. lead er kun synlig bag preview-gaten (P01) og i koden — den er ikke offentligt kommunikeret.

### Gaps
- Ingen prisside, vilkår eller kundecases er offentligt tilgængelige at sammenligne med.

---

## Kort benchmark-tabel (til direkte indsættelse)

| Dimension | Dialogbot (pr. repo 28/9 2026) | Kilde |
|---|---|---|
| Indgående AI-reception | Ja (viderestilling til Dialogbot-nummer, Twilio+Vapi) – simuleret testet, ikke live | docs/telephony/README.md |
| Webchat-widget | Ja (iframe-widget, kun godkendte domæner) – ikke verificeret på rigtig side | checkpoint 8 |
| Outbound-kampagner | Ja (9 kr./kontakt, maks. 2 forsøg/180 s, samtykke krævet) – ikke live | campaigns/service.py |
| Booking/kalender | Ja via iCal-adresse + iCal-feed (ingen OAuth) | checkpoint 22 |
| Leads/opgaver/rapporter | Ja | checkpoint 9–10 |
| SMS | Nej | checkpoint 14 |
| E-mail til slutkunder | Nej (kun konto-/notifikationsmail via Resend) | registry.py |
| Sprog | Dansk-først; samtalesprog konfigurerbart, kun dansk dokumenteret | business/router.py |
| Pris | Model A 1.495 kr./md. ekskl. moms (ingen leadgebyr) · Model B 149 kr./godkendt lead ekskl. moms · kampagne 9 kr./kontakt ekskl. moms · 25 % moms · Stripe måned bagud | agreements.py, money.py, campaigns/service.py |
| Inkluderede minutter/opkald | Ingen grænser kodet (forbrug bæres af Dialogbot) | money.py |
| Integrationer | iCal, Stripe, Resend, CVR, REST/OpenAPI; ingen CRM/e-conomic/Zapier/webhooks ud | registry.py |
| LLM | Anthropic `claude-opus-5` (standard) | app/config.py |
| STT | Deepgram Nova-3, dansk | telephony/vapi.py |
| TTS | ElevenLabs i dag; egen Røst-v3/Chatterbox-tjeneste på GPU som mål (21 designede stemmer + egen stemme), ikke produktionsgodkendt | docs/voice/* |
| Hosting | Render (Frankfurt) + Vercel + Supabase (eu-central-1); GPU planlagt Hetzner/RunPod EU | ADR-002, costs.md |
| Kostpris/min (leverandørsatser i repo) | Vapi $0,05 + Deepgram ≈ $0,006 + ElevenLabs ≈ $0,04 (LLM og Twilio ikke prissat); egen TTS €184/md. fast, break-even ≈ 5.000 min/md. | docs/voice/costs.md |
| Målt TTS-latens | RTX 4090 streaming: første lyd p95 0,66 s (server); L4 uden streaming p95 3,95 s | docs/voice/testing.md |
| GDPR | Dataansvarlig i Aarhus; EU-database; Vapi/Twilio/Deepgram/ElevenLabs/Anthropic "kan behandle data i USA"; AI-oplysning i alle kanaler; samtykke til alle AI-udgående opkald | web/src/app/privatliv/page.tsx |
| Onboarding | Selvbetjent plan + 5-trins telefoni med kontrolopkald og viderestillingsguide; Twilio-bundle manuelt af operatør | docs/telephony/README.md |
| Salg/demo | Demonummer, "Ring mig op nu", sælgerflow – simuleret | docs/sales/demo-calls.md |
| Modenhed | Privat preview; ~143 backend-tests + 48 E2E grønne mod simulerede leverandører; intet eksternt verificeret; juridik ikke gennemgået | implementation-progress.md |
