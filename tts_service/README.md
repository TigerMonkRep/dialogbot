# Dialogbot TTS-tjeneste

Separat proces til dansk talesyntese (Chatterbox Multilingual, `language_id="da"`). Kaldes kun af Dialogbot-API'et
med en hemmelig bearer-token. Se `docs/voice/` for arkitektur, drift og omkostninger.

| Miljøvariabel | Betydning |
|---|---|
| `TTS_SERVICE_TOKEN` | ≥ 32 tegn, samme værdi som API'ets `TTS_SERVICE_TOKEN` |
| `TTS_ENGINE` | `chatterbox` (produktion) · `fake` (kun test af mekanikken) |
| `MODEL_REPO` / `MODEL_REVISION` / `MODEL_T3` | Standard er Røst-v3: `CoRal-project/roest-v3-chatterbox-500m`, `7ce205cea6b3b36d9f60f18abb88ff21fa04ea0d`, `t3_mtl23ls_v2.safetensors`. Revisionen skal altid være et fuldt 40-tegns commit-hash (aldrig `main`) |
| `TTS_DEVICE` | `cuda` (GPU) eller `cpu` (kun til måling/udvikling – for langsom til telefoni) |
| `HF_HOME` | modelcache (volumen), fx `/models/hf` |
| `HF_TOKEN` | kun hvis Hugging Face kræver login for vægtene |
| `VOICE_STORAGE`, `VOICE_STORAGE_DIR`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VOICE_BUCKET` | læseadgang til private referenceklip |
| `TTS_QUEUE_LIMIT`, `TTS_QUEUE_TIMEOUT`, `TTS_GENERATION_TIMEOUT`, `TTS_MAX_CHARS`, `TTS_VOICE_CACHE` | kø, timeouts og grænser |

Test af mekanikken (uden vægte): `pip install -r tts_service/requirements-test.txt && pytest tts_service/tests`.
