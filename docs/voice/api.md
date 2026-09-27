# API-kontrakt – stemmer

Alle stier ligger under `/api/v1`. Browseren kalder dem via BFF'en `/api/backend/*` og skal sende
`x-requested-with: dialogbot` på mutationer. Fejl følger projektets format
`{code, message, field_errors, request_id}`. Den fulde maskinlæsbare kontrakt findes i `docs/openapi.json`.

## Kunde (arbejdsrum)

| Metode og sti | Rolle | Formål |
|---|---|---|
| `GET /workspaces/{ws}/voices` | medarbejder | Valgbare stemmer (kun aktive, platform eller eget arbejdsrum), motorstatus (`available`/`simulated`/`not_configured`), tildelinger, indstillinger |
| `GET /workspaces/{ws}/voices/{profile}` | medarbejder | Én stemme (404 hvis den tilhører et andet arbejdsrum) |
| `POST /workspaces/{ws}/voices/{profile}/preview` `{text?}` | medarbejder | WAV-prøve. Egen tekst højst `VOICE_PREVIEW_MAX_CHARS` (200), tælles og caches aldrig. Standardprøven caches pr. version. Svarheader `x-simulated: 1` ved testmotor. 429 ved dagsgrænse eller en prøve allerede i gang; 501 uden motor; 503 hvis motoren er utilgængelig eller optaget |
| `PUT /workspaces/{ws}/voices/settings` `{expected_version, default_profile_id, fallback, pronunciations}` | admin | Standardstemme, reservepolitik og udtaleordbog (versioneret). Genåbner tjek, der afhænger af stemmen |
| `PUT /workspaces/{ws}/voices/assignments/phone-numbers/{id}` `{voice_profile_id}` | admin | Assistentens stemme (null = standard) |
| `PUT /workspaces/{ws}/voices/assignments/campaigns/{id}` `{voice_profile_id}` | admin | Kampagnens stemme. Starter aldrig opkald og ændrer ikke pris |

## Operatør (`users.is_platform_operator`)

| Metode og sti | Formål |
|---|---|
| `GET/POST /operator/voice-rights` | Rettighedsposter (kode, model, datasæt, indtaleraftale) |
| `POST /operator/voice-rights/{id}/review` `{status, notes≥10}` | Verificér eller blokér efter faktisk gennemgang (navn og tid logges) |
| `GET/POST /operator/voices`, `PATCH /operator/voices/{id}` | Profiler: stabilt ID, visningsnavn, køn, dialekt, begrundelse, alder og klang (tom = ukendt), synlighed platform eller arbejdsrum |
| `POST /operator/voices/{id}/references` (rå WAV, ≤ 20 MB) | Referenceklip til privat lager under stemmens eget scope. Returnerer `{key, sha256, seconds, …}` |
| `POST /operator/voices/{id}/versions` | Uforanderlig version: `model_repo`, `model_revision` (40 hex), `references` (egne nøgler og checksum), `settings` (exaggeration, cfg_weight, temperature), `rights_record_ids` |
| `POST /operator/voice-versions/{v}/checks/run` | Automatiske kontroller: rights, normalization, synthesis_smoke |
| `POST /operator/voice-versions/{v}/checks/{listening_test\|telephony_test}` `{passed, evidence}` | Menneskelige kontroller med dokumentation. En lyttetest under målet afvises |
| `POST /operator/voice-versions/{v}/{submit\|reject\|approve\|activate\|suspend\|retire}` | Livscyklus. Godkend og aktivér afvises (409 med `missing`), hvis kontroller mangler |
| `POST /operator/voices/{id}/rollback` | Aktivér seneste anden godkendte version |
| `POST /operator/voice-versions/{v}/synthesize` `{text}` | Testklip af enhver version (WAV, caches ikke) |

## Telefoni (Vapi custom-voice)

`POST /voice/vapi/{voice_session_id}` kræver headeren `Authorization: Bearer <VAPI_SERVER_SECRET>` eller
`X-Vapi-Secret`. Kroppen er `{"message": {"type": "voice-request", "text": "...", "sampleRate": 24000}}`.
Svaret er rå mono 16-bit little-endian PCM ved den ønskede samplerate, uden WAV-header.

Headere på svaret:
- `x-sample-rate`
- `x-first-audio-ms`
- `x-simulated`

Status:
- 503: stemmen er suspenderet, eller motoren fejler, så Vapi skifter til `fallbackPlan`.
- 429: dagsgrænsen for tegn er nået.

Endpointet udfører aldrig forretningshandlinger.

Når en Dialogbot-stemme er valgt og aktiv, sætter assistentkonfigurationen (`assistant-request` og
kampagneopkald) `voice` til:

```json
{"provider": "custom-voice",
 "server": {"url": "<PUBLIC_BASE_URL>/api/v1/voice/vapi/<session>", "secret": "…", "timeoutSeconds": 20},
 "fallbackPlan": {"voices": [{"provider": "11labs", "voiceId": "<nummerets reservestemme>", "model": "…"}]}}
```

## Intern talemotor (`tts_service`, kun API'et er klient)

`POST /v1/synthesize` modtager:

```json
{"voice": {"version_id", "engine", "model_repo", "model_revision", "references": [{"key", "sha256"}], "settings"},
 "text": "<én normaliseret taleenhed>", "language": "da", "format": "pcm_s16le|wav", "sample_rate", "request_id", "session_id"}
```

Svaret er lyd med headerne `x-sample-rate`, `x-synthesis-ms`, `x-model-revision`, `x-watermark` og
`x-simulated`.

Status:
- 409 ved annulleret forespørgsel eller forkert modelrevision.
- 413 ved for lang tekst.
- 422 ved sprog ≠ da eller forkert format.
- 503 med `Retry-After`, når køen er fuld eller modellen ikke er klar.
- 504 ved timeout.

Øvrige endpoints: `DELETE /v1/requests/{id}` (annullér), `GET /health`, `GET /ready` (model indlæst og varm)
og `GET /metrics`.
