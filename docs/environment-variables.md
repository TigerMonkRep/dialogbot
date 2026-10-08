# Miljøvariabler — autoritativt manifest

Ét navn pr. hemmelighed. Render, Vercel, CI og lokal `.env` bruger disse navne. Ingen værdier her.

## Backend (Render `dialogbot-api-*` og `dialogbot-worker-*`, lokal `.env`)

| Variabel | Påkrævet | Modtager | Hentes fra | Bemærkning |
|---|---|---|---|---|
| `APP_ENV` | ja | API, worker | — | `dev` / `test` / `staging` / `prod`. staging+prod: kræver `SECRET_KEY`, forbyder dev-værktøjer. prod forbyder desuden `EMAIL_ADAPTER=simulated`. |
| `DATABASE_URL` | ja | API, worker, CI (test-DB) | Supabase → Connect → session pooler/direct, rolle `dialogbot_app` | `postgresql+psycopg://…`. Begrænset runtime-rolle. |
| `MIGRATION_DATABASE_URL` | staging/prod | Render pre-deploy (API) | Supabase → Connect → direct, rolle `dialogbot_migrate` | Kun til `alembic upgrade head`. Aldrig i worker. |
| `DB_SCHEMA` | Supabase | API, worker, migration | — | `dialogbot`. Lokalt/CI: udelad (= `public`). |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | nej | API, worker | — | Standard 5/5. Worker kan sættes til 2/2. |
| `SECRET_KEY` | staging/prod | API, worker | Render `generateValue` (API) → kopiér samme værdi til worker | ≥ 32 tegn. |
| `ENABLE_DEV_TOOLS` | nej | API | — | `true` kun i dev/test. Åbner `/api/v1/dev/*` (simuleret postkasse). |
| `AUTH_PROVIDER` | nej | API | — | `local`. `external` er reserveret og fejler lukket. |
| `SESSION_TTL_HOURS`, `INVITATION_TTL_HOURS`, `RESET_TTL_MINUTES`, `VERIFICATION_TTL_HOURS` | nej | API | — | Standard 336 / 72 / 60 / 48. |
| `EMAIL_ADAPTER` | ja | API, worker | — | `simulated` (dev/test/staging) eller `resend`. |
| `RESEND_API_KEY` | ved resend | worker (API kun hvis den sender synkront – det gør den ikke) | Resend → API Keys | Staging- og prod-nøgle adskilt. |
| `RESEND_WEBHOOK_SECRET` | ved resend | API | Resend → Webhooks → endpoint → *Signing secret* (`whsec_…`) | Uden den svarer `POST /api/v1/webhooks/resend` 503. Én pr. miljø. |
| `AI_PROVIDER` | nej | API | — | `none` (standard: AI-endpoints svarer 501), `anthropic`, eller `fake` (testdobbelt, kun dev/test – afvises ellers ved opstart). |
| `AI_MODEL_ID` | nej | API | Anthropic → Models | Standard `claude-opus-5`. Logges pr. kald i `ai_usage`. |
| `ANTHROPIC_API_KEY` | ved anthropic | API | Anthropic Console → API Keys (sæt månedligt forbrugsloft) | Uden nøgle nægter processen at starte med `AI_PROVIDER=anthropic`. |
| `AI_EFFORT` | nej | API | — | `low` / `medium` (standard) / `high`. |
| `AI_MAX_OUTPUT_TOKENS` | nej | API | — | Standard 2048 (inkl. tænkning). |
| `AI_SERVER_FALLBACKS` | nej | API | — | `true` (standard): Anthropics server-side fallback ved politik-afvisning (`fallbacks: "default"`). Sæt `false`, hvis `AI_MODEL_ID` ikke har en standard-fallback. |
| `WEBCHAT_DAILY_REPLY_LIMIT` | nej | API | — | Standard 300. Højeste antal AI-svar pr. arbejdsrum pr. døgn i web-widgetten (udgiftsværn). Derudover: 20 beskeder pr. samtale, 60 nye samtaler i timen pr. widget. |
| `VAPI_SERVER_SECRET` | ved telefoni | API | Vælges af jer (≥ 32 tegn) | Dialogbot sætter den selv som Bearer-header, når numre importeres i Vapi. Uden den svarer `POST /api/v1/webhooks/vapi` 503. |
| `VAPI_ORG_ID` | anbefalet | API | Vapi → Organization → Settings | Webhooks fra andre Vapi-organisationer afvises. |
| `TELEPHONY_PROVIDER` | nej | API + worker | — | `none` (standard: intet købes, kunder står i "Forbindelse klargøres"), `live` (Twilio + Vapi) eller `fake` (kun dev/test). Se `docs/telephony/owner-setup.md`. |
| `TWILIO_ACCOUNT_SID` | ved live | API + worker | Twilio Console (hovedkonto `AC…`) | Underkonti pr. arbejdsrum oprettes under denne. |
| `TWILIO_API_KEY_SID` / `TWILIO_API_KEY_SECRET` (el. `TWILIO_AUTH_TOKEN`) | ved live | API + worker | Twilio → API keys & tokens | **Server-only.** Returneres og logges aldrig. |
| `TELEPHONY_NUMBER_COUNTRY` / `TELEPHONY_NUMBER_TYPE` | nej | API + worker | — | Standard `DK` / `local` (kræver virksomhedsdokumentation). `mobile` kræver ingen dokumenter. |
| `TELEPHONY_VERIFY_NUMBER_ID` | ved live | API | Vapi-id for Dialogbots kontrolnummer | Bruges til kontrolopkaldet, der læser en 6-cifret kode op for kundens nummer. |
| `VAPI_MODEL_PROVIDER` | nej | API | — | Standard `anthropic`. Verificér, at Vapi understøtter den valgte model. |
| `VAPI_VOICE_JSON` / `VAPI_TRANSCRIBER_JSON` | nej | API | Vapi-dashboardet | Valgfri JSON-objekter, der sendes uændret som `voice`/`transcriber`. Transskribering er som standard dansk ElevenLabs Scribe v2 realtime med Deepgram Nova-3 som reserve; sættes `VAPI_TRANSCRIBER_JSON`, bruges den i stedet (uden reserve). Stemmen vælges normalt pr. nummer under Indstillinger → Telefoni; `VAPI_VOICE_JSON` bruges kun for numre uden egen stemme. |
| `VAPI_API_KEY` | nej | API + worker | Vapi → Organization → API Keys → **Private** key | Udgående kampagneopkald (`POST /call`). Uden den kan kampagner forberedes, men ikke startes (501). `VAPI_API_URL` kan overstyre `https://api.vapi.ai`. **Server-only.** |
| `STRIPE_SECRET_KEY` | nej | API + worker | Stripe → Developers → API keys → Secret key (brug `sk_test_…` først) | Betalingskort (Checkout i setup-tilstand) og månedsfakturaer. Uden den svarer betaling 501, og der trækkes intet. **Server-only.** |
| `STRIPE_WEBHOOK_SECRET` | nej | API | Stripe → Developers → Webhooks → endpoint `…/api/v1/webhooks/stripe` (hændelser `checkout.session.completed`, `invoice.*`) → Signing secret `whsec_…` | Verificerer Stripe-hændelser (kort gemt, faktura betalt/fejlet). **Server-only.** |
| `TTS_ENGINE` | nej | API | `none` (standard) · `http` (separat taletjeneste) · `fake` (kun dev/test; en mærket tone) | Dialogbots egne danske stemmer. `none`: telefonen bruger den eksisterende ElevenLabs-stemme. API'et nægter at starte med `http` uden URL/token og med `fake` i staging/prod |
| `TTS_SERVICE_URL` / `TTS_SERVICE_TOKEN` | ved `http` | API | Adressen på `tts_service` og en tilfældig token (≥ 32 tegn), samme værdi på TTS-hosten | Server-til-server. **Server-only.** |
| `TTS_TIMEOUT_SECONDS` | nej | API | standard 20 | Timeout pr. taleenhed; bruges også som Vapis `timeoutSeconds` |
| `VOICE_STORAGE` / `VOICE_STORAGE_DIR` / `VOICE_BUCKET` | nej | API, worker, TTS | `local` (dev) eller `supabase` + privat bucket `voice-private` | Referenceklip, aftaler, prøvecache. Aldrig offentlig |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | ved `supabase` | API, worker, TTS | Supabase → Settings → API | Privat lager server-side. **Server-only, aldrig `NEXT_PUBLIC_`.** |
| `VOICE_PREVIEW_DAILY_LIMIT` / `VOICE_PREVIEW_MAX_CHARS` / `VOICE_CALL_DAILY_CHAR_LIMIT` | nej | API | standard 40 / 200 / 400.000 | Forbrugsloft for stemmeprøver og opkaldssyntese pr. arbejdsrum og døgn |
| `ELEVENLABS_API_KEY` | nej | API | ElevenLabs → API Keys (samme konto som i Vapi → Integrations) | Lydprøver af stemmerne på Stemmer-siden og knappen "Hør stemmen" under Telefoni. Prøven laves én gang og gemmes. Uden den vises ingen lytteknap; opkald virker stadig. **Server-only.** |
| `ELEVENLABS_AGENT_SECRET` | nej | API | Vælg selv (32+ tilfældige tegn) | Kun til test af ElevenLabs Agents som opkaldsmotor: ElevenLabs sender den som header `X-Dialogbot-Secret` til `/api/v1/webhooks/elevenlabs/init`. **Server-only.** |
| `ELEVENLABS_WEBHOOK_SECRET` | nej | API | ElevenLabs → Agents → Settings → Post-call webhook (HMAC-secret) | Verificerer `/api/v1/webhooks/elevenlabs/post-call`, som gemmer opkaldet i indbakken. **Server-only.** |
| `CVR_USERNAME` / `CVR_PASSWORD` | nej | API + worker | Gratis system-til-system-adgang fra Erhvervsstyrelsen (skriv til cvrselvbetjening@erst.dk) | Knappen "Slå op" ved CVR på virksomhedssiden (navn, adresse, branche, status) og tjek af reklamebeskyttelse i sælgerflowet, og "Profiler at følge" i operatørens sociale-medier-dashboard (worker'en laver den daglige portion). Uden dem svarer opslaget 501. `CVR_URL` kan overstyre endpointet. **Server-only.** |
| `SALES_WORKSPACE_ID` | nej | API | Id på Dialogbots eget salgsarbejdsrum (se `docs/sales/demo-calls.md`) | Demo-opkald: "Ring mig op nu" på forsiden, demonummeret og sælgerflowet `/app/operator/sales`. Uden den siger forsiden ærligt, at demo-opkald åbner ved lanceringen. `SALES_CALL_FROM`/`SALES_CALL_TO` (standard 08:00/20:00, dansk tid) og `SALES_MAX_CALLS_PER_HOUR` (standard 20) begrænser hjemmesidens opkald. |
| `SOCIAL_PROVIDER` | nej | API + worker | — | `none` (standard: intet genereres eller postes), `live` (rigtige opslag på Facebook, Instagram og TikTok) eller `fake` (testdobbelt, kun dev/test). Se `docs/social-media.md`. `live` kræver mindst `META_PAGE_ACCESS_TOKEN` eller `TIKTOK_CLIENT_KEY`. |
| `SOCIAL_REQUIRE_APPROVAL` | nej | API + worker | — | `false` (standard: opslag går ud af sig selv på deres tidspunkt) eller `true` (de venter som kladder, til en operatør godkender dem). |
| `SOCIAL_PLATFORMS` | nej | API + worker | — | Standard `facebook,instagram,tiktok`. Kun platforme på listen **og** med gyldige nøgler får opslag. |
| `SOCIAL_WEEKDAYS` / `SOCIAL_PLAN_DAYS_AHEAD` | nej | API + worker | — | Ugedage (mandag=0) med opslag, standard `0,2,4` (man/ons/fre), og hvor mange dage frem kladderne laves, standard 3. |
| `SOCIAL_MAX_LATE_MINUTES` | nej | worker | — | Standard 360. Er et tidspunkt mere forsinket end det, når workeren det, springes opslaget over i stedet for at gå ud på et underligt tidspunkt. |
| `SOCIAL_SITE_URL` | nej | API + worker | — | Standard `https://www.dialogbot.dk`. Linket i Facebook-opslagene. |
| `META_PAGE_ID` / `META_PAGE_ACCESS_TOKEN` | ved Facebook | API + worker | Meta for Developers → Graph API Explorer / System User (se `docs/social-media.md`) | Dialogbots Facebook-side og dens langlivede sidetoken. **Server-only.** |
| `META_INSTAGRAM_USER_ID` | ved Instagram | API + worker | `GET /{page-id}?fields=instagram_business_account` | Instagram-virksomhedskontoen, der er knyttet til siden. Bruger samme token. `META_GRAPH_VERSION` (standard `v23.0`) kan hæves. |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | ved TikTok | API + worker | TikTok for Developers → din app | **Server-only.** |
| `TIKTOK_SCOPES` | nej | API + worker | Standard `user.info.basic,video.publish,user.info.stats,video.list` | De to sidste giver følgertal og engagement til operatør-dashboardet. Scopes skal også være slået til på appen hos TikTok, og kontoen skal godkende igen (`social_connect tiktok-url/tiktok-code`), når de ændres. |
| `TIKTOK_REFRESH_TOKEN` | ved TikTok | API + worker | Kun første gang; `python -m scripts.social_connect tiktok-code …` gemmer det i databasen i stedet | TikToks refresh-token skifter ved hver brug; det nye gemmes krypteret i databasen (`CREDENTIALS_KEY`), og miljøvariablen bruges ikke bagefter. |
| `CREDENTIALS_KEY` | ja for handlinger (staging/prod) | API + worker | `python -m scripts.credentials_key` (32 tilfældige bytes, base64url) | Envelope-kryptering af kundernes legitimationer (OAuth-tokens, webhook-hemmeligheder). Uden den i staging/prod vises connectors med hemmeligheder som "ikke tilgængelig"; dev/test afleder en nøgle af `SECRET_KEY`. Samme værdi på API og worker. **Server-only.** |
| `CREDENTIALS_KEY_PREVIOUS` | nej | API + worker | Den gamle `CREDENTIALS_KEY` under rotation | Gamle rækker kan stadig læses; nye skrives med den nye nøgle. Fjern, når alle er genkrypteret. **Server-only.** |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | nej | API + worker | Google Cloud Console → APIs & Services → Credentials → OAuth client (Web). Redirect-URI: `{PUBLIC_BASE_URL}/api/v1/integrations/oauth/google_calendar/callback`. Scopes: `calendar.events`, `calendar.freebusy`, `openid`, `email` | Google Kalender-connectoren. Uden dem vises den som "ikke tilgængelig". I Googles "Testing"-tilstand højst 100 testbrugere og 7 dages tokens; produktion kræver OAuth-verificering. **Server-only.** |
| `MICROSOFT_OAUTH_CLIENT_ID` / `MICROSOFT_OAUTH_CLIENT_SECRET` / `MICROSOFT_OAUTH_TENANT` | nej | API + worker | Microsoft Entra → App registrations (multitenant). Redirect-URI: `{PUBLIC_BASE_URL}/api/v1/integrations/oauth/microsoft_calendar/callback`. Delegerede rettigheder `Calendars.ReadWrite`, `User.Read`, `offline_access`. Tenant standard `common` | Microsoft 365-kalender-connectoren. Publisher verification anbefales. **Server-only.** |
| `CONNECTORS_PROVIDER` | nej | API + worker | `live` (standard) eller `fake` (kun dev/test) | `fake` = simulerede kalender/SMS/webhooks; alt mærkes simuleret. Nægtes uden for dev/test. |
| `SMS_DEFAULT_SENDER` | nej | API | Fx `Dialogbot` (≤ 11 tegn) | Afsender for SMS, når et arbejdsrums navn ikke kan bruges som alfanumerisk afsender. |
| `VAPI_MODEL` | nej | API | — | Sprogmodellen i telefonsamtaler (standard `claude-haiku-4-5-20251001`, fordi hurtige svar lyder mest naturligt; en Anthropic-model, Vapi ikke kender, erstattes af den). Telefoni kræver hurtige svar; vælg en model, som Vapi understøtter, og mål latenstiden ved prøveopkald. |
| `EMAIL_FROM` | ved resend | worker | Verificeret afsenderdomæne i Resend | `Dialogbot <noreply@mail.<domæne>>` |
| `PUBLIC_BASE_URL` | ja | API | Render-URL | Bruges i OpenAPI/links. |
| `FRONTEND_BASE_URL` | ja | API, worker | Vercel-URL | Links i mails (verificering, reset, invitation). |
| `WORKER_POLL_SECONDS`, `WORKER_LEASE_SECONDS`, `WORKER_MAX_ATTEMPTS` | nej | worker | — | 1 / 60 / 5. |
| `LOG_LEVEL` | nej | API, worker | — | `INFO`. |
| `SEED_DEMO_PASSWORD` | nej | manuel kørsel (kun dev/staging) | — | Seed nægter `prod`. |
| `TEST_DATABASE_URL` | CI/lokal test | pytest | — | Separat database; skemaet droppes ved hver kørsel. |

## Frontend (Vercel-projekt med Root Directory `web`)

| Variabel | Påkrævet | Miljø | Bemærkning |
|---|---|---|---|
| `API_BASE_URL` | ja | Production, Preview | Render-API'ets URL (staging til Preview, prod til Production). **Server-only** – ingen `NEXT_PUBLIC_`-variant findes eller må oprettes. |
| `PREVIEW_GATE` | nej | Production, Preview | — | **Slået til som standard**: forsiden `/` og `/signup` ligger bag den midlertidige adgangsside `/preview` (P00), indtil platformen er klar. `off` åbner siderne (fx lokalt). Indloggede brugere og invitationslinks (`/signup?next=/invite/…`) slipper igennem. |
| `PREVIEW_ACCESS_CODES` | ved gate | samme | Vælges af jer | Kommaseparerede invitationskoder, mindst 8 tegn hver (kortere ignoreres). Store/små bogstaver er ligegyldige. **Server-only.** |
| `PREVIEW_COOKIE_SECRET` | ved gate | samme | Tilfældig streng ≥ 32 tegn | Signerer adgangscookien `db_preview` (httpOnly, 30 dage). Udskiftes den, skal alle indtaste en kode igen. Mangler den, låser ingen kode op (fejler lukket). |

Der findes ingen `NEXT_PUBLIC_*` hemmeligheder. Browseren kender kun sit eget origin; sessionen ligger i cookien `db_session` (httpOnly, Secure, SameSite=Lax), det valgte arbejdsrum i `db_ws`.

## Senere milepæle (navne reserveret, ikke læst af koden endnu)

`AI_PROVIDER`, `AI_MODEL_ID`, `ANTHROPIC_API_KEY`, `VAPI_WEBHOOK_SECRET`, `TWILIO_MESSAGING_SERVICE_SID`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY` (eneste offentlige), `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID`/`MS_CLIENT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (kun backend, kun til Storage-adapteren), `STORAGE_BUCKET_SOURCES`, `STORAGE_BUCKET_EXPORTS`.
