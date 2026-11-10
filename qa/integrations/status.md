# Integrationsstatus – ærlighedsmatrix (X26 / DB-018)

Kørsel 2026-11-10, integrations-qa. Branch `qa/fix-2026-11-10`. Grundlag: kildekoden (fil:linje nedenfor), pytest mod egen DB
(`qa_integ`) med leverandører stubbet ved adaptergrænsen, og Playwright mod den fulde stak med fake-adaptere. Ingen
rigtige kald, ingen env-værdier læst.

**Tilstande:** `live` = rigtig leverandørkode, aktiv når env er sat · `live (ubekræftet)` = rigtig kode, men aldrig kørt mod
leverandøren her · `test-mode` = rigtig leverandør i testtilstand · `adapter-only` = kun testdobbelt/stub i koden ·
`not-implemented` = ikke bygget.

## 1. Kundens integrationer – `/app/indstillinger?ark=integrationer` (API `GET /workspaces/{id}/integrations`)

| Integration | Reel tilstand (kode) | Uden env-variabler: API → UI | Med fake-adaptere (e2e-stak): API → UI | Match? |
|---|---|---|---|---|
| Google Kalender (OAuth + Calendar v3) | live (ubekræftet). `connectors/calendar.py:80` GoogleCalendarClient, `oauth.py:60` PKCE + scopes `calendar.events calendar.freebusy openid email` | `not_implemented` + «Kræver … GOOGLE_OAUTH_CLIENT_ID/SECRET» → «Ikke tilgængelig», ingen Forbind-knap; connect → 501, ingen state-række | `connected`, `simulated: true` → «Forbundet (simuleret)», «Forbindelsen virker (simuleret).» | ✔ — men ✘ ved delvist samtykke: bliver «Forbundet» uden `calendar.events` (**F-IQ-02**, S2) |
| Microsoft 365-kalender (Graph v1.0) | live (ubekræftet). `calendar.py:118` | som Google (MICROSOFT_OAUTH_…) | som Google | ✔ |
| Dialogbots kalender (åbningstider + iCal) | live (indbygget) | `not_connected` + «Slå online booking til …» → «Ikke forbundet» | samme | ✔ |
| SMS-bekræftelser (Twilio REST via platformens konto) | live (ubekræftet). `connectors/sms.py:129` POST `/Messages.json` | `not_implemented` + «SMS kræver … TELEPHONY_PROVIDER» → «Ikke tilgængelig» | «Forbundet (simuleret)»; SMS havner i `WORLD.sms`, run `simulated` | ✘ live: «Forbundet»/«Forbindelsen virker» uden Twilio-kald, og forbliver grøn efter Twilio 401 (**F-IQ-01**, S1) |
| Webhook / Zapier / Make (signeret HTTP POST, outbox-retry) | live (ingen leverandørkonto nødvendig) | `not_connected` (reelt tilgængelig) | «Forbundet (simuleret)», levering simuleret | ✔ |
| HubSpot, Pipedrive, e-conomic, Dinero, Billy, Microsoft Bookings, SimplyBook.me, Ordrestyring, Minuba, Planday | not-implemented (`connectors/__init__.py` COMING) | `not_implemented`, `availability: coming` → listet under «Via Zapier eller Make»/«På vej» som tekst, intet kort, ingen knap; connect → 404 | samme | ✔ |
| Krypteringsnøgle (CREDENTIALS_KEY) i staging/prod | — | uden nøgle: alle oauth/secret-connectors `not_implemented` med «Kræver … CREDENTIALS_KEY» | — | ✔ |

## 2. Platformens kapabiliteter – `GET /integrations/capabilities` (læses af shell, opsætning, reception, viden, webchat)

| Kapabilitet | Reel tilstand | Uden env | Fake-stak (målt 2026-11-10) | Match? |
|---|---|---|---|---|
| E-mail (Resend) | live: `integrations/email.py` + signeret webhook | `simulated` (simuleret postkasse) | `simulated` | ✔ |
| Indgående telefoni (Vapi + Twilio) | live (ubekræftet) | `not_implemented` | **`available`** trods TELEPHONY_PROVIDER=fake | ✘ (**F-IQ-05**, S3) |
| Udgående kampagner (Vapi POST /call) | live (ubekræftet) | `not_implemented` | `not_implemented` (ingen VAPI_API_KEY) | ✔ |
| Dialogbots stemmer (TTS-tjeneste) | live via `tts_service/` | `not_implemented` | `simulated` | ✔ |
| Kalender og online booking | live | `available` | `available` | ✔ |
| Betaling (Stripe) | test-mode (sk_test_ indtil ejeren går live) | `not_implemented` | `not_implemented` | ✘ med kun STRIPE_SECRET_KEY: `available` uden webhook-hemmelighed; sk_test vises som `available`, `/billing/account` har intet test-felt (**F-IQ-03**, S2) |
| AI (Anthropic) / webchat / vidensimport | live | `not_implemented` | `simulated` | ✔ |
| CVR-opslag | live | `not_implemented` | `not_implemented` | ✔ |
| Handlinger (connectors) | live | `available` | `simulated` | ✔ |

## 3. Dialogbot Privat-apps (`addons.live_status`)

| Integration | Reel tilstand | Uden env | Med `fake` | Match? |
|---|---|---|---|---|
| 17TRACK (Pakker) | live (ubekræftet), `privat/parcels.py:49` | «Kommer snart» (`coming_soon`), `tracker()` → TrackError | FakeTracker – **også i APP_ENV=prod**, appen «available» uden «simuleret» | ✘ (**F-IQ-04**, S2) |
| Duffel (Rejser, flytilbud) | live (ubekræftet – travel.py: «NOT externally verified against live keys») | «Kommer snart» | FakeProvider i alle miljøer | ✘ (**F-IQ-04**) |
| Travelpayouts/Aviasales (Rejser) | live (ubekræftet), kræver token **og** marker | «Kommer snart» | som Duffel | ✘ token uden marker → app «available», søgninger altid tomme (**F-IQ-06**, S2) |
| Google/Microsoft i Privat Kalender | samme OAuth-klient og callback som Erhverv | — | — | ikke testet separat (e2e-privat) |

## 4. Øvrige integrationer i koden (gennemgået i kode, ikke dybdetestet her)

| Integration | Reel tilstand | Hvad UI/API påstår | Match? |
|---|---|---|---|
| Vapi (webhook/assistent) | live; webhook 503 uden VAPI_SERVER_SECRET | telefoni-status fra `telephony/platform.py:111`; prøveopkald har `simulated`-flag | ✔ (voice-qa ejer detaljer) |
| Soniox / Speechmatics / ElevenLabs Scribe (STT) | live bag Stemmetest/broen; uden nøgle «Mangler adgang» (`stt/adapters.py:44`) | operatør-UI viser «Mangler adgang» | ✔ |
| Stripe-webhook | live; signatur + replay (`webhooks/router.py:37`) | — | ✔ (billing-qa) |
| Resend-webhook | live; 503 uden RESEND_WEBHOOK_SECRET | registry-note | ✔ |
| Vercel Web Analytics / GA4 (operatør) | live; «ikke sat op» uden token | — | ikke testet |
| Meta/TikTok (social autoposting) | live, `SOCIAL_PROVIDER` none/fake/live, fake afvist i staging/prod | — | ikke testet (uden for X26-kunde-UI) |
| Google Places (salgskanal/Privat) | live; uden nøgle «tydeligt fiktive demo-data» | — | ikke testet |
| Public API-webhooks | live, outbox i worker | — | api-contract-qa |

## 5. Oversigten «Alle indstillinger» (`web/src/app/app/(admin)/indstillinger/page.tsx`)

| Tile | Viser | Burde | Match? |
|---|---|---|---|
| Kalender / Forbundne systemer | «Klar» for simulerede forbindelser, uden «simuleret» | «(simuleret)» som på integrationssiden | ✘ (**F-IQ-07**, S3) |
| Abonnement og fakturaer | altid «Klar» (også når Stripe er `not_implemented`) | følg `/billing/account.configured` | ✘ (F-IQ-07) |
| Webhooks og Zapier (Vis teknik) | altid «Klar» | følg om en sink er forbundet | ✘ (F-IQ-07) |

## 6. Env-variabler (kun NAVNE; `tests/qa/test_qa_integ_X26_env.py`)

| Navn | Kode læser i | docs/environment-variables.md | render.yaml API | render.yaml worker |
|---|---|---|---|---|
| GOOGLE_OAUTH_CLIENT_ID/SECRET | API + worker (privat.calendar_sync → oauth.refresh) | ✔ API + worker | ✘ | ✘ |
| MICROSOFT_OAUTH_CLIENT_ID/SECRET | API + worker | ✔ | ✘ | ✘ |
| CREDENTIALS_KEY | API + worker | ✔ | ✔ | ✔ |
| TELEPHONY_PROVIDER, TWILIO_* | API + worker (platform-jobs, SMS) | ✔ | ✘ | ✘ |
| VAPI_API_KEY | API + worker (kampagne-dispatch) | ✔ | ✘ (men worker har `fromService` til den) | ✔ (fromService) |
| VAPI_SERVER_SECRET | API + **worker** (`campaigns/service.py:194`) | ✘ kun «API» | ✔ | ✘ |
| STRIPE_SECRET_KEY | API + worker (invoice_due) | ✔ | ✘ | ✘ |
| STRIPE_WEBHOOK_SECRET | API | ✔ | ✘ | – |
| RESEND_API_KEY / RESEND_WEBHOOK_SECRET | worker / API | ✔ | ✔ | ✔ |
| TRACK17_API_KEY | API + worker | ✔ | ✔ | ✔ |
| DUFFEL_ACCESS_TOKEN, TRAVELPAYOUTS_TOKEN/MARKER | API | ✔ | ✔ | – |
| SONIOX_API_KEY | API | ✔ | ✘ | – |
| SONIOX_MODEL | API | ✘ | ✘ | – |

→ **F-IQ-08** (S2; S1 hvis dashboardet også mangler VAPI_SERVER_SECRET på workeren – kontrollér navnet i Render).

## 7. E07 – bookingkommunikation (DB-018)

| Variant (krav E07) | Findes? | Bevis |
|---|---|---|
| Kvittering for forespørgsel | ✘ | ingen skabelon (`email_templates.samples()`, `sms_templates`) |
| Bekræftet aftale | delvist: SMS-skabelon `booking`, kun når assistenten kalder `send_sms_bekraeftelse` i en samtale; intet ved selve bookingen; ingen e-mail til kunden | `test_e07_inventory_of_booking_messages` |
| Påmindelse | ✘ | ingen outbox-type/handler med booking/remind |
| Foreslået ændring | ✘ | – |
| Flyttet | delvist: samme SMS-skabelon bærer den nye tid efter `flyt_tid`; intet sendes af sig selv | inventory-testen |
| Aflyst | ✘ (skabelonen afviser `no_booking` efter aflysning) | inventory-testen |
| Ejeren skal handle | ✘: fejler kalenderskrivningen, står bookingen og forbindelsen bliver «Fejl», men ejeren får ingen besked (jf. F-EB-05-BK15) | `test_e07_delivery_failure_and_owner_attention` |
| Leveringsfejl | delvist: SMS-fejl → run `failed` med årsag, assistenten bedes sige det; «SMS sendt» = accepteret af Twilio, ingen leveringskvittering | samme test |

UI'et påstår ikke, at E07-skabelonerne findes (ingen E07-side; «Book for en kunde» siger ærligt «Kunden får ingen SMS endnu»). → **E07 = not-implemented**, intet ærlighedsfund.

## Bemærkninger
- Blandet dev-tilstand `TELEPHONY_PROVIDER=fake` + `CONNECTORS_PROVIDER=live`: SMS-connectoren er «tilgængelig», men `sms.send` kalder `FakeTwilio._req`, som ikke findes → 500 (kun dev/test; ikke indberettet).
- SMS-handlingen har `confirm=False`, mens integrationssidens intro siger «Kunden bekræfter altid først» (sendt videre til security-privacy).
