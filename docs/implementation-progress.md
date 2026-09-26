# Implementeringsfremdrift

Vedligeholdes ved hvert checkpoint. Statusord: implementeret · testet lokalt/CI · deployet · eksternt verificeret.

## Checkpoint 16 — 26. september 2026 (stemmeprøve og ryddet brugerflade)

| Del | Status | Bevis |
|---|---|---|
| `POST /workspaces/{id}/phone-numbers/{nid}/voice-preview` (ejer/admin): ElevenLabs text-to-speech med den valgte (også ikke-gemte) stemme og hilsenen → `audio/mpeg`; intet gemmes; uden `ELEVENLABS_API_KEY` 501 `voice_preview_not_configured` | testet | `test_voice_preview` |
| Knappen "Hør stemmen" under Telefoni → Stemme og talestil; sprog-siden henviser dertil i stedet for "ikke tilkoblet" | implementeret, E2E | rejse 14 |
| Interne Stitch-koder (A06, G01, S03 …) og "milepæl"-jargon fjernet fra brugerfladen | implementeret | build + E2E |

**Ikke eksternt verificeret:** et rigtigt kald til ElevenLabs (kræver nøglen i Render).

## Checkpoint 15 — 26. september 2026 (dansk stemme i telefonen)

| Del | Status | Bevis |
|---|---|---|
| Transskribering på dansk som standard: `transcriber = {deepgram, nova-3, language: da}`; `VAPI_TRANSCRIBER_JSON` overstyrer | testet | `test_danish_transcriber_voice_and_speaking_style` |
| Stemme pr. nummer: `phone_numbers.voice_id`/`voice_model`/`speaking_style` (Alembic `24414f5bd46b`); ElevenLabs (`11labs`) med Multilingual v2 / Flash v2.5 (sprog låst til `da`) / Turbo v2.5; nummerets stemme går forud for `VAPI_VOICE_JSON`; valideret id og model; kun ejer/admin | testet | samme |
| Telefonprompt `phone-v2`: naturligt dansk talesprog, korte sætninger, du-form, danske vendinger, tal/beløb/klokkeslæt som de siges, ét spørgsmål ad gangen; virksomhedens talestil tilføjes uden at kunne ændre fakta eller regler | testet | samme |
| UI: "Stemme og talestil" under Indstillinger → Telefoni med advarsel, når ingen dansk stemme er valgt | implementeret, E2E | rejse 14 udvidet |
| `ai.conversation` følger nu AI-udbyderen (webchat og telefon er rigtige kundekanaler) → "Aktiv AI" vises, når Anthropic er sat op | testet | `test_ai_assistant` |

**Ikke eksternt verificeret:** lydkvalitet, latenstid og at Vapi accepterer `nova-3`+`da` og den valgte ElevenLabs-model — kræver et rigtigt prøveopkald. Dialekt kommer fra stemmevalget (ElevenLabs-bibliotek eller klonet stemme med samtykke); talestil styrer kun ordvalg.

## Checkpoint 14 — 26. september 2026 (callback-tidsvinduer i webchat)

| Del | Status | Bevis |
|---|---|---|
| `GET /public/webchat/{key}/callback-windows`: "Hurtigst muligt" + formiddag (8–12) / eftermiddag (12–16) i dag og næste hverdag i arbejdsrummets tidszone; et vindue tilbydes kun, mens mindst én time er tilbage; weekender springes over | testet | `tests/test_callback_windows.py` (2) |
| "Bliv kontaktet" med tidsrum kræver telefonnummer; `leads.callback_from/to` (Alembic `c89e73f71c6d`); opgaven hedder "Ring … op – <tidsrum>" med frist ved vinduets start; et udløbet vindue afvises (422) | testet | `test_contact_with_callback_window_…` |
| Chatvinduet viser "Hvornår må vi ringe?"; henvendelsessiden viser "Ønsker opkald …" | implementeret, E2E | rejse 12 udvidet |

**Ikke implementeret:** verifikation af kundens nummer (kræver SMS-udbyder) og automatisk opkald i vinduet (kræver udgående telefoni).

## Checkpoint 13 — 25. september 2026 (månedlig afregningsoversigt)

| Del | Status | Bevis |
|---|---|---|
| `GET /workspaces/{id}/billing/statement?month=ÅÅÅÅ-MM` (ejer/admin): model A = abonnement fra aftalen gældende ved månedens udgang (godkendte henvendelser ændrer ikke totalen); model B = sum af godkendte henvendelsers pris-snapshots; kalendermåned i arbejdsrummets tidszone; `Money`-totaler (25 % moms, half-up, hele øre) | testet | `tests/test_billing_statement.py` (3): 14 leads under B = 208.600 / 52.150 / 260.750 øre |
| Status altid `preview`, `invoicing: not_implemented` – ingen faktura, ingen betaling | testet | samme |
| UI `/app/billing` (månedsskift, poster, netto/moms/i alt, "ikke en faktura"); menupunktet "Fakturering" aktiveret | implementeret, E2E | rejse 16 |

**Ikke implementeret:** fakturaer, kreditnotaer, tvister (reglerne ligger i `billing/money.py`), kampagnepakker (9 kr., max 2 forsøg, 180 s) og betaling — kræver Stripe og kampagnemodulet.

## Checkpoint 12 — 25. september 2026 (medarbejdersvar i webchat)

| Del | Status | Bevis |
|---|---|---|
| `conversations.mode` (ai/staff) og `conversation_messages.author_user_id` | implementeret, migreret | Alembic `19a35ecb7df3`; op/ned + `alembic check` |
| Medarbejder (staff+) svarer i indbakken → samtalen skifter til `staff`, assistenten svarer ikke (intet modelkald), kundens beskeder gemmes; "Giv tilbage til assistenten" (auditlogget) – modellen ser herefter medarbejdersvar som tidligere assistentsvar | testet | `test_staff_takeover_silences_assistant_and_reaches_visitor` |
| Telefonopkald kan ikke besvares i chatten (409) | testet | `test_phone_conversations_cannot_be_answered_in_chat` |
| Widgetten henter nye svar hvert 5. sekund (højst 30 min uden aktivitet) og viser dem som "Medarbejder"; indbakken opdaterer sig selv og markerer "Venter på svar" | implementeret, E2E | rejse 15 (1440 + 390) |

## Checkpoint 11 — 25. september 2026 (milepæl B: indgående telefoni via Vapi)

| Del | Status | Bevis |
|---|---|---|
| `phone_numbers` (E.164 + udbyder-id, unik, pr. arbejdsrum) og `calls` (unik pr. udbyder-opkalds-id) | implementeret, migreret | Alembic `46c794fe9e35`; op/ned + `alembic check` |
| `POST /api/v1/webhooks/vapi`: 503 uden `VAPI_SERVER_SECRET`; Bearer eller legacy `X-Vapi-Secret` i konstanttid; nummer→arbejdsrum via Vapi-nummer-id eller E.164 | testet | `tests/test_telephony.py` (7) |
| `assistant-request`: midlertidig assistent med prompt kun fra godkendt viden + telefonregler (`phone-v1`), hilsen med AI-oplysning; ukendt/inaktivt nummer eller ingen godkendt viden → `{"error": …}` | testet | `test_assistant_request_*` |
| `end-of-call-report`: opkald + transskription som `phone`-samtale (system/tool-beskeder udeladt), henvendelse + opgave "Ring tilbage" når kunden talte og nummeret kendes; idempotent; ukendte numre `unmatched` | testet | `test_end_of_call_*`, `test_silent_or_anonymous_*` |
| Kapabilitet `telephony.inbound` = available kun med `VAPI_SERVER_SECRET`; tjek `telephony.test_call`/`forwarding` kræver et rigtigt opkald på et aktivt nummer inden for 30 dage | testet | `test_setup_checks_need_a_real_call` |
| UI: Indstillinger → Telefoni (vejledning, webhook-URL, numre, seneste opkald); indbakke og henvendelser viser kanal "Telefon" | implementeret, E2E | rejse 14 (1440 + 390) |

**Ikke eksternt verificeret:** ingen Vapi-konto eller nummer; Vapis HMAC-variant er ikke understøttet (Bearer er Vapis standard). Twilio bruges gennem Vapi, så Dialogbot modtager ikke Twilio-webhooks direkte endnu. Udgående kampagneopkald kommer i milepæl C/D.

## Checkpoint 10 — 25. september 2026 (milepæl B: daglige rapporter)

| Del | Status | Bevis |
|---|---|---|
| `daily_reports` (unik pr. arbejdsrum og lokal dato, uforanderligt snapshot) og `report_settings` (e-mail til/fra, afsendelsestime) | implementeret, migreret | Alembic `5a2d1bff4ed7`; op/ned + `alembic check` |
| Døgn i arbejdsrummets tidszone (`zoneinfo`, også 23/25-timers døgn ved sommertid); tal: samtaler, kundebeskeder, AI-svar (ok/afvist/fejl, tokens, estimeret pris), nye/godkendte/afviste henvendelser + godkendt beløb i hele øre, opgaver oprettet/løst/over frist | testet | `tests/test_reports.py` (5) |
| Workeren kører planlægning hvert minut: efter den lokale afsendelsestime gemmes gårsdagens rapport én gang, og ejere/administratorer får én e-mail (outbox-dedupe) | testet | `test_scheduler_snapshots_once_and_emails_owner_once` |
| API: liste, dag (endelig / foreløbig for i dag), indstillinger (admin+); pris- og beløbsfelter kun for ejer/admin | testet | `test_api_today_is_preliminary_roles_and_isolation` |
| UI `/app/reports` (dagsliste, nøgletal, nye henvendelser, e-mailindstilling); menupunktet "Rapporter" peger nu på siden | implementeret, E2E | rejse 13 (1440 + 390) |

**Ikke eksternt verificeret:** e-mail kræver Resend (se §4); staging kører simuleret e-mail.

## Checkpoint 9 — 25. september 2026 (milepæl B: henvendelser, opgaver og prisaftale)

| Del | Status | Bevis |
|---|---|---|
| `leads`, `tasks`, `reception_agreements` (versioneret, kun tilføjelser) | implementeret, migreret | Alembic `477adf47202c`; op/ned + `alembic check` |
| Tre adskilte akser på en henvendelse: kvalificering (ikke vurderet/kvalificeret/ikke relevant), forløb (ny/kontaktet/vundet/tabt), afregning (afventer/godkendt/afvist). Én henvendelse pr. samtale | testet | `tests/test_leads.py` (7) |
| "Bliv kontaktet" i webchatten (navn + e-mail eller telefon + samtykke) → henvendelse, opgave "Kontakt …" med frist +24 t, og e-mail (`email.new_lead`) til ejere/administratorer. Gentagen indsendelse opdaterer i stedet for at duplikere | testet (API + E2E) | `test_webchat_contact_creates_lead_task_and_notification`, E2E rejse 12 |
| Webchat-prompten beder kunden bruge knappen ved ønske om kontakt/tilbud/booking (promptversion `assistant-v1+webchat-v1`) | testet | — |
| Prisaftale: ejeren vælger model A (1.495 kr./md., intet leadgebyr) eller B (149 kr. pr. godkendt henvendelse); listepriser fra produktreglerne, hver ændring er en ny version; "der faktureres ikke endnu" | testet | `test_model_b_approval…`, `test_model_a_approval…` |
| Godkendelse (ejer/admin) er en idempotent domænehandling (`Idempotency-Key`), kræver kvalificeret henvendelse og en aftale, og gemmer aftaleversion + pris i hele øre (B: 14.900 netto / 3.725 moms / 18.625 brutto; A: 0). Afgjort én gang; derefter er kvalificeringen låst, og senere aftaleskift ændrer ikke snapshot. Afvisning kræver begrundelse | testet | samme |
| Opgaver: opret, tildel (kun medlemmer), afslut/genåbn, filtre (åbne/færdige/mine) | testet | `test_tasks_crud…` |
| UI: `/app/leads` (filtre), henvendelsesside (redigering, afregning, opgaver, link til samtale), `/app/tasks`, Indstillinger → Prisaftale, "Opret henvendelse" fra en samtale; menupunktet "Henvendelser" peger nu på siden | implementeret, E2E | rejse 12 (1440 + 390) |

**Ikke implementeret endnu:** fakturering/betaling, tvister på godkendte henvendelser (reglerne ligger i `billing/money.py`), medarbejdersvar direkte i chatten.

## Checkpoint 8 — 25. september 2026 (milepæl B: webchat-widget på ekstern origin + indbakke)

| Del | Status | Bevis |
|---|---|---|
| `webchat_settings`, `conversations`, `conversation_messages` | implementeret, migreret | Alembic `501a6eb0eaeb`; op/ned + `alembic check` |
| Indlejring: `<script src=".../api/v1/public/webchat/loader.js" data-dialogbot-key="wk_…">`. Loaderen viser kun en knap, når `/status` svarer `available` med CORS for netop dette domæne. Chatten kører i en iframe på API-origin; CSP `frame-ancestors` = godkendte domæner; besøgstoken bliver i iframen (sessionStorage), kun dets SHA-256 gemmes | implementeret, testet (API + E2E) | `tests/test_webchat.py` (10), E2E rejse 11: kundeside på `localhost:4000` chatter, fremmed side på `:4001` får ingen knap |
| Skrivninger kun fra chatvinduet (Origin = API-origin), token pr. samtale, samme 401 for ukendt samtale/forkert token, anden widgetnøgle kan ikke læse samtalen | testet | `test_conversation_multi_turn…`, `test_other_widget_key…` |
| Flerturs-svar via `ai.service.complete_logged` (kun godkendt viden, `ai_usage.purpose=webchat`), afvisninger maskeres, AI-oplysning i vinduet | testet | — |
| Udgiftsværn: 1.000 tegn/besked, 20 beskeder/samtale, 60 nye samtaler/time/widget, `WEBCHAT_DAILY_REPLY_LIMIT` (300) svar/døgn/arbejdsrum | testet | `test_limits` |
| Admin (W01) `/app/settings/webchat`: slå til/fra (kun når AI, godkendt viden og domæner er på plads), domæner (https; http kun localhost i dev/test), hilsen, indlejringskode, ny nøgle; auditlog | implementeret, E2E | rejse 11 |
| Indbakke `/app/inbox` + samtalevisning (medarbejder+); navigationens "Indbakke" peger nu på den | implementeret, E2E | rejse 11 |
| Opsætning: `reception.webchat` fuldføres af tjekket `webchat.widget`, som kræver en rigtig AI-udbyder (ikke simuleret) og at chatvinduet er åbnet i en iframe på et godkendt domæne inden for 30 dage; ændringer gør tjekket forældet | testet | `test_setup_check_needs_real_provider_and_evidence` |

**Ikke eksternt verificeret:** kræver `AI_PROVIDER=anthropic` på Render (sat af brugeren) og en rigtig hjemmeside med koden. Svar fra medarbejdere og overdragelse til leads/opgaver kommer i næste trin.

## Checkpoint 7 — 25. september 2026 (ny forside P01 + midlertidig adgangsside P00)

**Grundlag:** Stitch-eksporterne `stitch_dialogbot_2` (P01 forside) og `stitch_dialogbot_3` (P00 midlertidig landingsside med adgangskontrol), desktop + mobil. Kildefiler i `design-reference/landing/` (screen.png i eksporten var ødelagte; siderne er renderet lokalt med `design-reference/tools/stitch-render.mjs`).

| Del | Status | Bevis |
|---|---|---|
| P00 `/preview`: forhåndskode (tjekkes på serveren i `/api/preview/unlock`, konstanttids-sammenligning, 0,8 s forsinkelse ved forkert kode) → signeret httpOnly-cookie `db_preview` | implementeret, E2E-testet | rejse 1 (forkert + rigtig kode) og 10 |
| Gate i `proxy.ts` (slået til som standard; `PREVIEW_GATE=off` åbner): `/` og `/signup` → `/preview?next=…`; undtaget: indloggede, invitationslinks (`/signup?next=/invite/…`); fejler lukket uden hemmelighed/koder | implementeret, E2E-testet | rejse 10 |
| Venteliste `POST /api/v1/waitlist` (offentlig): samtykke påkrævet, e-mail normaliseres, gentagen tilmelding opdaterer svar, samme svar for ny/eksisterende e-mail (ingen enumeration), honeypot | implementeret, testet | `tests/test_waitlist.py` (4), Alembic `c432350c7efd` op/ned + `alembic check` |
| P01 `/`: hero med eksempelsamtale, to spor (fører hensigt videre til signup), brancheskifter, tre trin + kontrol, overblik, FAQ (`<details>`), afsluttende CTA med prismodellerne A/B | implementeret, E2E-screenshot 1440 + 390 | rejse 1 |

**Ærlighed – bevidste afvigelser fra Stitch:** ingen offentlig demokode ("DGB-PREVIEW" ville gøre beskyttelsen virkningsløs), ingen "Latency < 280 ms", "100 % dansk hosting", "148 virksomheder", CVR/ApS-oplysninger, "Q2 åbning" eller stemmeprøve, der ikke findes. P01 har et "Privat preview"-banner; samtaler er mærket som eksempler; FAQ siger, hvad der virker i dag, og hvad der er planlagt. "Prøv en samtale" er erstattet af "Start opsætning"/"Sådan fungerer det". Links til sider, der ikke findes (priser, privatliv, vilkår), er udeladt.

**Tilføjet efter merge (PR #7):** `/privatliv` (ikke bag gaten) med dataansvarlig Dialogbot, Abildgade 18, 8200 Aarhus, Danmark; formål, retsgrundlag (samtykke), opbevaring (højst 24 mdr.), databehandlere og rettigheder. Linket fra samtykketeksten og sidefødderne. `python -m scripts.waitlist export|delete <e-mail>` (køres i Render-shell) eksporterer CSV og sletter på anmodning; testet i `tests/test_waitlist.py`.

**Deploy:** beskyttelsen er aktiv uden opsætning (P00 er første side). For at kunne låse op med en kode kræves `PREVIEW_ACCESS_CODES` og `PREVIEW_COOKIE_SECRET` i Vercel; uden dem virker ingen kode, men ventelisten og login gør.

## Checkpoint 6 — 25. september 2026 (milepæl B: Anthropic-adapter bag interface)

**Grundlag:** Resend-webhook merget som `669a67a` (PR #3).

| Del | Status | Bevis |
|---|---|---|
| `AI_PROVIDER` (`none`/`anthropic`/`fake`), `AI_MODEL_ID` (standard `claude-opus-5`), `ANTHROPIC_API_KEY`, `AI_EFFORT`, `AI_MAX_OUTPUT_TOKENS`, `AI_SERVER_FALLBACKS`; fejler lukket uden nøgle og afviser `fake` uden for dev/test | implementeret, testet | `test_config_fails_closed` |
| `AIProvider`-interface + `AnthropicProvider` (officiel SDK `anthropic==1.8.0`, `beta.messages.create`, prompt caching på systemblokken, `output_config.effort`, `fallbacks: "default"` med beta `server-side-fallback-2026-07-01`; kun tekstblokke returneres) | implementeret, testet med stubbet SDK-klient | `test_anthropic_request_shape_and_usage`, `test_anthropic_fallback_model_is_recorded_and_can_be_disabled` |
| Prompt bygges kun af godkendt viden (kladder, nyere kladder af godkendte emner og andre arbejdsrums viden kommer aldrig med); uden godkendt viden → 409 uden modelkald | testet | `test_prompt_contains_only_approved_knowledge_…`, `test_no_approved_knowledge_is_409_…` |
| `ai_usage`-log pr. kald: arbejdsrum, bruger, formål, udbyder, anmodet/faktisk model, promptversion `assistant-v1`, vidensrevision, input/output/cache-tokens, estimeret pris (µUSD, kun for kendte modeller), latens, request-id, fejlkode | implementeret, migreret, testet | Alembic `43c189532412`; op/ned testet; `alembic check` ren |
| Afvisning (`stop_reason=refusal`) maskeres med neutral dansk tekst og logges `refused`; 429 → 503 `ai_rate_limited`; øvrige udbyderfejl → 502 `ai_provider_error` (logges `error`) | testet | `test_anthropic_refusal_and_errors`, `test_refusal_is_masked_and_logged` |
| `POST /workspaces/{id}/assistant/preview` (staff+), `GET /workspaces/{id}/ai/usage` (admin+); fremmed arbejdsrum → 404; uden udbyder → 501 `ai_not_configured` | testet | `test_usage_summary_is_per_workspace_and_admin_only`, `test_not_configured_is_501_…` |
| Kapabilitet `ai.assistant_preview` (available/simulated/not_implemented efter udbyder). `ai.conversation` forbliver `not_implemented` → UI viser ikke "Aktiv AI" | implementeret, testet | — |

| R06 "Test assistenten" i videnscentret (medarbejder+): ét spørgsmål ad gangen mod `/assistant/preview`, viser svar, model, promptversion, vidensrevision, tokens og prisestimat; admin ser 30-dages forbrug. Markeret som intern test; "simuleret model" vises ved `fake`. Uden udbyder vises den ærlige pladsholder | implementeret, E2E-testet (1440 + 390) | `web/e2e/journeys.spec.ts` rejse 9; E2E-workflow kører `AI_PROVIDER=fake` |

**Ikke eksternt verificeret:** ingen Anthropic-nøgle endnu; model-ID `claude-opus-5` er ikke kaldt mod API'et fra dette miljø. Staging kører `AI_PROVIDER=none`.

**Præcis næste handling:** Bruger: `docs/services-setup.md` §5 (nøgle + forbrugsloft, to variabler i Render). Claude: preview-kald på staging → `ai_usage`-række med `served_model` og tokens. Derefter webchat-widget på ekstern origin.

## Checkpoint 5 — 25. september 2026 (milepæl B: Resend-leveringswebhook)

**Grundlag:** milepæl A merget som `85e15b2` (PR #2).

| Del | Status | Bevis |
|---|---|---|
| `POST /api/v1/webhooks/resend` (Svix-signatur, 5-min replay-vindue, idempotent på `svix-id`) | implementeret, testet | `tests/test_resend_webhook.py` (10 tests), heraf én fast testvektor genereret med det officielle `svix`-bibliotek |
| `email_deliveries.provider_message_id`/`provider_status`/`provider_status_at`, tabel `webhook_events` | implementeret, migreret | Alembic `773ead23336e`; op/ned testet; `alembic check` ren |
| Status kun fremad (sent → delivery_delayed → delivered → failed/bounced/complained); `status` (afsendelsesresultat) røres aldrig | testet | `test_status_only_moves_forward` |
| Ukendte beskeder og ikke-sporede hændelser (fx `email.opened`) gemmes som `unmatched`/`ignored` | testet | `test_unknown_message_and_untracked_event_types_…` |
| `ResendEmailAdapter` gemmer nu mailteksten og udbyder-id i eget felt (overskrev før `body_text`) | implementeret | — |
| Uden `RESEND_WEBHOOK_SECRET` svarer endpointet 503 (aldrig "accepteret" uden signaturkontrol) | testet | `test_not_configured_answers_503` |

**Ikke eksternt verificeret:** ingen Resend-konto, domæne eller nøgle endnu. Staging kører fortsat `EMAIL_ADAPTER=simulated`.

**Præcis næste handling:** Bruger: opsætning pr. `docs/services-setup.md` §4 (domæne + DNS, API-nøgle, webhook-endpoint, tre variabler i Render). Claude: derefter "Send test event" fra Resend og en rigtig verificeringsmail → `provider_status=delivered` på staging. Parallelt: Anthropic-adapter bag interface (AI_PROVIDER/AI_MODEL_ID).

## Checkpoint 4 — 25. september 2026 (milepæl A: design-fidelitet mod Stitch)

**Gren/PR:** `claude/cool-wozniak-ho00tr` → https://github.com/TigerMonkRep/dialogbot/pull/2 (draft). CI (backend + web) grøn på `d2edbb7`.
**Referencer:** Stitch-eksporten (44 skærme, desktop + mobil) ligger i `design-reference/latest/stitch_dialogbot/`; skærmoversigt og DESIGN.md også hentet via Stitch MCP (`design-reference/stitch/`).
**Metode:** `design-reference/tools/stitch-render.mjs` renderer hver Stitch-`code.html` offline (Tailwind v3 kompileret fra skærmens egen config, lokale fonte, faner via `STITCH_EVAL`). `compare.mjs` logger ind i appen og laver side-om-side-billeder ved 1440 px (desktop-reference) og 390 px (mobil-reference). Kørt mod lokal API + PostgreSQL med seed-data.

| Skærm | Rute | Desktop 1440 | Mobil 390 | Bemærkninger |
|---|---|---|---|---|
| App-skal (guide) | /app/setup, /onboarding/* | matchet (G01-header, footer) | matchet (header, bundnav, Mere-ark) | "Aktiv AI" kun når `ai.conversation` er `available` |
| App-skal (admin) | /app/knowledge, /app/settings/*, /app/not-yet | matchet (K01-sidebjælke + topheader) | matchet (header, 5-punkts bundnav) | Stitch bruger topnav i opsætning og sidebjælke i drift – fulgt pr. skærm |
| G01–G05 | /app/setup | matchet | matchet | Persona (O05), AI-forslag og H01-support vist som ikke tilgængelige |
| A06/O01/O02 | /onboarding/business, /onboarding/workspace | matchet | matchet | O02 viser rigtig manuel viden; ingen "konfidens"-tal eller udtræk |
| O03/O04 | /onboarding/goals, /onboarding/languages | kortdesign fra G01 | kortdesign fra G01 | Ingen selvstændig Stitch-skærm |
| K01–K05, R05/R06 | /app/knowledge?tab=… | matchet (alle faner) | matchet (K01) | Strukturerede formularer i stedet for JSON; K05 sammenligning; K01/R05/R06 ærlige tomtilstande |
| A01–A05 | /signup, /login, /verify-email, /password/*, /invite/[token] | centreret kolonne | matchet (A04) | Kun mobilreference findes i Stitch |
| S02, S08, S09 | /app/settings/team, /profile, /activity | designsystem (admin-skal) | designsystem | Ingen Stitch-skærm; S08 skrivebeskyttet (intet API til navn/sprog) |
| P01 | / | P04–P08-stil | P04–P08-stil | Ingen egen Stitch-skærm; kun sande påstande |

**E2E (Playwright, `web/e2e`, workflow `.github/workflows/e2e.yml`):** otte rejser + tastatur/fokus, hver ved 1440 og 390 px, mod Next production build → FastAPI + outbox-worker → PostgreSQL (seed). 18/18 grønne lokalt. Screenshots, HTML-rapport og logs uploades som artefakt `e2e-<sha>`. Rejserne er defineret ud fra de flows, der findes (blueprint §9.1 findes ikke i repoet): (1) A01→A03→A06 med bevaret hensigt, (2) A02 fejl/husket destination/log ud, (3) A04 nulstilling, (4) O01→O03→O04 med gem-før-navigation, (5) K03→K05 kladde→godkend, (6) G01/G05 med ærlige ikke-tilgængelige trin, (7) S02→A05 invitation, (8) roller (læser/medarbejder/admin).

**Fejl fundet og rettet undervejs:** åbent redirect via `?next=//host` og `/\host` (proxy, login, signup); død session-cookie efter nulstilling; manglende "ingen næste handling"-tilstand på mobil; O01 viste "ugemte ændringer" efter gem.

**Ikke gjort endnu:** G03-wrapper (guidet side pr. opgave); staging-screenshots (netværkspolitikken blokerer stadig `*.vercel.app`/`*.onrender.com` i denne container).

**Præcis næste handling:** grøn CI på PR #2 (inkl. E2E) → merge → kontrollér staging visuelt (bruger, eller Claude i en session med åbne værter) → milepæl B (Resend-webhook).

## Checkpoint 3 — 25. september 2026 (overtagelse, milepæl A-design)

**Baseline genkontrolleret:** `main` = `cb79a99` (Stitch-commit er på main). 26/26 pytest mod lokal PostgreSQL 16, `npm run build` grøn (22 ruter). Render `dialogbot-api-staging` live på `cb79a99` (deploy `dep-dar7koe7bikc73auval0`, via Render-API). `/health/ready` og Vercel-URL kunne **ikke** kaldes direkte: sessionens netværkspolitik blokerer `*.onrender.com` og `*.vercel.app`, og Vercel-forbindelsen har ikke adgang til projektet.

**Fundet og rettet (browserkontrolleret lokalt, Chromium 1440/390 px):**

| Fejl | Årsag | Rettelse |
|---|---|---|
| Hele designsystemet virkede ikke på staging: ingen farver, spacing, typografi eller `lg:`-layout | Kommentaren i `globals.css` indeholdt `stitch_dialogbot/*/code.html`; `*/` lukkede kommentaren, så `@theme`-blokken blev en ugyldig regel og droppet af Next' CSS-pipeline (CSS 22 KB → 36 KB efter rettelse) | Kommentar rettet |
| Ikoner vist som tekst (`check_circle`, `schedule`) og systemfont i stedet for Inter/Manrope | Fonte hentet fra Google Fonts ved runtime | Self-hostet via `material-symbols`, `@fontsource-variable/inter`, `@fontsource-variable/manrope` i `@layer base`; ingen runtime-kald til Google (også GDPR-venligere) |

**Ikke gjort / blokeringer:**
- **Designreferencerne findes ikke i repoet eller containeren:** `design-reference/latest/stitch_dialogbot/` (44 HTML), `legacy-html/` (128 HTML), `Dialogbot-Backend-Blueprint.md`, `canonical-requirements.json`, `canonical-demo-data.json`, `implementation-backlog.csv`, `Dialogbot-Claude-Full-Platform-Prompt.md`. Uden dem kan side-for-side-sammenligning (§3) og de otte brugerrejser (blueprint §9.1) ikke udføres.
- Kendt afvigelse set lokalt: mobilheaderen (390 px) klipper ikonerne til højre.

**Præcis næste handling:**
1. **Bruger:** læg afleveringspakken i repoet (fx `design-reference/` og `docs/handoff/`) og tillad `dialogbot-api-staging.onrender.com` og `dialogbot-sepia.vercel.app` i miljøets netværksindstillinger.
2. **Claude:** efter merge — screenshot staging mod Stitch-referencer ved 1440/390 px, ret afvigelser, byg S08/S09/G03/G04, tilføj Playwright-CI.

## Checkpoint 2 — 25. september 2026 (milepæl A, delvist)

**Commits:** `f24c75f` (etape 1) → `60726df` (milepæl A: frontend, infra, docs).
**GitHub:** https://github.com/TigerMonkRep/dialogbot — `main` på `c874941`, fuld historik (eksternt verificeret via `git ls-remote`).
**CI:** GitHub Actions run #1 grøn for både `CI` (48 s) og `Web` (35 s) på `c874941`.
**Supabase (eksternt verificeret):** projekt `dialogbot-staging`, ref `zofdupmpcokvcvstsozm`, eu-central-1, 10 USD/md. bekræftet af bruger. Schema `dialogbot` med roller `dialogbot_migrate` (ejer) og `dialogbot_app` (DML, ingen DDL). Alembic `94af55693109` anvendt som offline-SQL via forbindelsen: 19 tabeller i `dialogbot`, 0 i `public`, `anon`/`authenticated` uden adgang, security-advisor 0 fund. Adgangskoder udleveret én gang i chat (ikke i repo). Udestår i dashboard: bekræft at `dialogbot` ikke er i *Exposed schemas*.
**Deploy:** Render og Vercel ikke oprettet endnu (forbindelser ikke tilkoblet).

### Færdigt siden etape 1

| Del | Status | Bevis |
|---|---|---|
| Baseline verificeret | testet lokalt | 26/26 pytest mod PostgreSQL 16.15, ruff ren, `alembic check` ren, låste versioner stemmer |
| Next.js-frontend `web/` (Next 16.3, TS, Tailwind 4, designsystem) | implementeret, build verificeret | `npm run build` → 21 ruter; `tsc --noEmit` ren |
| Ruter: `/`, `/signup`, `/login`, `/verify-email`, `/password/forgot`, `/password/reset`, `/invite/[token]`, `/onboarding/{workspace,business,goals,languages}`, `/app/setup`, `/app/knowledge`, `/app/settings/team`, `/app/settings/business` | implementeret | HTTP-gennemløb mod live API+worker: login-cookie, redirect for uautentificeret, plan/viden/team server-renderet med rigtige data, CSRF-afvisning, tjek-kørsel via proxy, logout |
| BFF-auth (httpOnly-cookie, same-origin proxy, CSRF-header, no-store) | implementeret, testet på HTTP-niveau | `docs/ADR-002-hosting-and-services.md` |
| Backend: `APP_ENV=staging`, `DB_SCHEMA`, pool-størrelser, Resend-adapter | implementeret; schema-migration testet lokalt | 19 tabeller i schema `dialogbot`; Resend **ikke eksternt verificeret** |
| `infra/render.yaml`, `infra/supabase-roles.sql`, `web/vercel.json`, `.github/workflows/web.yml` | implementeret | — |
| `docs/services-setup.md`, `docs/environment-variables.md`, `docs/ADR-002` | skrevet | — |

### Ikke gjort / blokeringer

- **Render/Vercel** — ikke tilkoblet; Render-blueprint klar. Vercel-forbindelse set aktiv, men frontend-preview er meningsløs uden API.
- **Browserkontrol** (390/1440 px, tastatur, fokus, layout mod Stitch-referencer) — ikke udført; ingen browser i miljøet.
- Frontend mangler: P02–P09 (offentlige sider), S08 profilside, S09 aktivitetsvisning, G03-wrapper med eksempler, G04-drawer, K02 kilder. Disse er ikke skjult: `/app/setup` viser ikke-implementerede trin som "Ikke tilgængelig".
- Budget med to scenarier — udestår, indtil priser slås op ved tilkobling.
- Resend-leveringswebhooks, Anthropic/Vapi/Twilio/Stripe/kalender — milepæl B–D.

### Præcis næste handling

1. **Bruger:** tilkobl Render-forbindelsen (eller opret Blueprint manuelt fra `infra/render.yaml`); indsæt `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `DB_SCHEMA=dialogbot`, `FRONTEND_BASE_URL`, `PUBLIC_BASE_URL`, `EMAIL_FROM` som secrets. Hent hosts fra Supabase Connect (session pooler til runtime, direct til migration).
2. **Claude:** verificér `/health/ready` på Render → Vercel-import (Root `web`, `API_BASE_URL`) → gennemfør konto→viden→plan på preview-URL og notér links her.
3. **Uafhængigt af adgang:** fortsæt milepæl A-frontend (P02–P09, S08, S09) og forbered Resend-webhook + Anthropic-adapter (milepæl B).
