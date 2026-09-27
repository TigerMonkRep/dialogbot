# Drift og opsætning – stemmemodulet

Hvad du skal oprette og konfigurere, i rækkefølge. Intet af det kræver nye betalte ressourcer, før trin 4, og
dér skal budgettet aftales først.

## 1. Kode og database (sker ved merge)

- Migration `a8a4f6f5ffaf_voice_library` kører som Render pre-deploy (`alembic upgrade head` med
  `MIGRATION_DATABASE_URL`). Den tilføjer:
  - `voice_rights_records`, `voice_profiles`, `voice_versions`, `workspace_voice_settings`,
    `voice_sessions` og `voice_usage`;
  - `phone_numbers.voice_profile_id`, `campaigns.voice_profile_id` og `users.is_platform_operator`.
- **Rollback af migrationen:** `alembic downgrade 7769c9d94fe1` (testet lokalt op → ned → op).
  Stemmedata går tabt ved downgrade. Tag en backup først (Supabase → Database → Backups eller `pg_dump`).
- Kommandoen kan køres i Render → dialogbot-api-staging → Shell:
  - `python -m scripts.grant_operator grant info@fyrster.dk` giver dig operatørrollen.
  - `python -m scripts.voices_register_coral` opretter rettighedsposter (ikke gennemgået) og to
    kladde-profiler.

## 2. Supabase – privat lager

1. Supabase → Storage → New bucket `voice-private`, **Public: off**. Tilføj ingen policies. Kun
   service-role-nøglen (server-side) skal have adgang; browseren får aldrig en storage-URL.
2. På Render (API **og** worker) og på TTS-tjenesten sættes:
   - `VOICE_STORAGE=supabase`
   - `VOICE_BUCKET=voice-private`
   - `SUPABASE_URL=https://zofdupmpcokvcvstsozm.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY` (Supabase → Settings → API → service_role). Nøglen indsættes kun i
     Render- og TTS-hostens dashboard, aldrig i Git eller chat.
3. Backup: referenceklip kan genskabes fra datasættet ved den fastlåste revision. Indtaleraftaler og egne
   optagelser skal have en separat backup (download eller en anden bucket).

## 3. Vercel

Ingen nye variabler. Frontenden kalder kun `/api/backend/*` (BFF). Service-role-nøgler og TTS-tokens må
aldrig have `NEXT_PUBLIC_`-præfiks.

## 4. TTS-ressource (GPU) – kræver aftalt budget

Taletjenesten er `tts_service/Dockerfile`: CUDA 12.4, én model pr. GPU, varm hele tiden.

- **Region:** EU (Tyskland/Finland), tæt på Frankfurt, hvor API'et ligger på Render.
- **Hardware:** NVIDIA-GPU med ≥ 16 GB VRAM. Chatterbox bruger ca. 5–7 GB, og der skal være plads til
  voice-cache.
- **Pilotforslag:**
  - Hetzner GEX44 (RTX 4000 SFF Ada, 20 GB) til fast månedspris, eller
  - RunPod Secure Cloud L4 pr. time.

  Se `costs.md`. Render har ingen GPU'er.
- **Samtidighed:** ikke målt endnu. Kør `python -m voice_pipeline.eval.bench tts --concurrency 1,2,4 --hardware "<navn>"`,
  og sæt antal replikaer efter p95 < 1,5 s for hele svaret.
- **Miljøvariabler på TTS-hosten:**
  - `TTS_SERVICE_TOKEN` (≥ 32 tegn, tilfældig)
  - `MODEL_REPO=ResembleAI/chatterbox`
  - `MODEL_REVISION=<40-tegns commit, efter licensgennemgang>`
  - `TTS_DEVICE=cuda`
  - `HF_HOME=/models/hf` (volumen)
  - `HF_TOKEN` (kun hvis påkrævet)
  - `VOICE_STORAGE`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VOICE_BUCKET`
  - `TTS_QUEUE_LIMIT=8`
- **På Render (API):**
  - `TTS_ENGINE=http`
  - `TTS_SERVICE_URL=https://<tts-host>`
  - `TTS_SERVICE_TOKEN=<samme>`
  - `TTS_TIMEOUT_SECONDS=20`
  - valgfrit: `VOICE_PREVIEW_DAILY_LIMIT`, `VOICE_CALL_DAILY_CHAR_LIMIT`

  API'et nægter at starte med `TTS_ENGINE=http` uden URL og token.
- **Health:**
  - `GET /health`: liveness.
  - `GET /ready` med token: modellen er indlæst og varmet op, ellers 503.
  - Opstarten henter vægte første gang og kan tage flere minutter (HEALTHCHECK start-period er 300 s).

## 5. Telefoni

Intet nyt skal oprettes. Vapi-nummeret og `VAPI_SERVER_SECRET` bruges til både webhook og custom-voice.
Reservestemmen er nummerets ElevenLabs-stemme under Indstillinger → Telefoni.

Talegenkendelse (Deepgram nova-3, `da`) og dialogmodel (Claude via Vapi) er uændrede og findes allerede.

**Mangler for en rigtig testsamtale:**
- et dansk nummer eller det eksisterende Vapi-testnummer;
- en aktiv, godkendt stemme;
- TTS-hosten fra trin 4.

## 6. Driftsalarmer (forslag)

- `/ready` ≠ 200 i mere end 2 min → alarm (Uptime Robot eller Better Stack mod TTS-hosten med token-header).
- API-logs med `tts_unavailable`, `tts_busy` og `voice_not_active`: tæl pr. time. Mere end 1 % af
  voice-requests → alarm.
- `voice_sessions.stats`: p95 af `ttfa_ms_list` over 1500 ms → undersøg.
- Stigning i `voice_sessions.fallback` → reservestemmen bruges; find årsagen.

## 7. Rollback i drift

- **Stemme:** `POST /operator/voices/{id}/rollback`, eller `suspend`, hvorefter nye kald bruger
  reservestemmen med det samme.
- **Motor:** sæt `TTS_ENGINE=none` på Render. Alle opkald bruger så den eksisterende ElevenLabs-stemme.
- **Kode:** redeploy forrige commit på Render og Vercel.

## 8. Nye stemmer (import)

Se `recording-brief.md`. Kort fortalt:

1. Upload WAV via operatørvisningen, eller brug `voice_pipeline/` til store mængder.
2. Opret en version med referenceklip og rettighedspost.
3. Kør kontroller.
4. Lyttetest (`voice_pipeline.eval.listening_test`).
5. Telefontest.
6. Godkend og aktivér.
