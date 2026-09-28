# Testresultater – stemmemodulet

Kørt 27. september 2026 i udviklingscontaineren: 4 vCPU, 15 GB RAM, **ingen GPU**, PostgreSQL 16 lokalt.
**Al lyd i disse tests er simuleret** (`TTS_ENGINE=fake`, en tone). Rigtig dansk syntese er ikke kørt, fordi
huggingface.co (modelvægte og CoRal-TTS) er blokeret af miljøets netværkspolitik. Se "Ikke bestået / ikke kørt".

## Automatiske tests

| Kommando | Resultat | Hvad det dækker |
|---|---|---|
| `pytest` (backend, PostgreSQL) | 142 bestået | Hele regressionssuiten inkl. de nye stemmetests nedenfor |
| `pytest tests/test_voice_danish.py` | bestået | 4.100 tal (0–2.100 + 2.000 tilfældige op til 10 mio.) staves og parses tilbage til samme værdi. 14 eksempler (datoer, beløb, klokkeslæt, telefonnumre i par, e-mail). Udtaleordbog (hele ord). Taleenheder splitter aldrig en værdi. Testsættet: 110 sætninger i 9 kategorier; alle cifre udtales, alle `must_say` findes, nægtelser tabes ikke |
| `pytest tests/test_voices.py` | 7 bestået | Operatør-only. Version kræver fastlåst revision. Referenceklip skal tilhøre stemmen og matche checksum. Rettigheder `failed` indtil verificeret. Simuleret syntese tæller ikke som rigtig. Lyttetest under målet afvises. Godkendelse uden kontroller giver 409. Privat stemme er usynlig for andre arbejdsrum (404). Prøve-WAV er mærket simuleret. Tekst over 200 tegn giver 422. Dagsgrænse giver 429. Læser har ingen adgang (403). Opsætningstjekket kræver afspillet standardprøve af den aktuelle version. Nummerstemme giver `custom-voice` med ElevenLabs-reserve, `transcriber.language=da` og session med opkalds-ID. Rå PCM uden WAV-header. **Ny version midt i et opkald ændrer ikke det igangværende opkalds lyd; et nyt opkald får den nye.** Rollback. Suspendering giver 503, og næste opkald bruger reservestemme med registreret årsag. **3 gentagne voice-requests opretter ingen bookinger eller henvendelser.** Stats uden tekst. Kampagnestemme ændrer ikke status og pris, og et andet arbejdsrum får 404. Motor ikke konfigureret giver 501; motor utilgængelig giver 503. Cache-nøgler er adskilt pr. scope og version, invalidering virker, sti-traversal afvises |
| `pytest tts_service/tests voice_pipeline/tests` | 7 bestået | Tjenesten: auth, `/ready`, kun dansk, forkert modelrevision giver 409, PCM/WAV, resampling 24→8 kHz, forkert referencechecksum afvises, annullering før start, fuld kø giver 503 med Retry-After, kø-timeout, to stemmer skiftevis lækker ikke. Pipeline: Parquet med `{bytes, path}`-lyd læses uden `datasets`-dekoderen, original samplerate bevares, fjendtlig sti (`../../etc/passwd`) skrives aldrig uden for importmappen, tomme rækker registreres, QC flager clipping, lang pause og ikke-dansk tekst, referencevalg (6–12 s, rene klip) |
| `alembic upgrade head` → `downgrade -1` → `upgrade head` → `alembic check` | OK, ingen drift | Migration `a8a4f6f5ffaf` |
| `ruff check app tests scripts client voice_pipeline tts_service`, `tsc --noEmit`, `next lint` | OK | |

## Browser (Playwright, desktop 1440 og mobil 390)

Rejse 23, "Stemmer": bestået på begge viewports. Forløbet:

1. Operatøren gennemgår tre rettighedsposter og opretter en privat pilotstemme.
2. Upload af reference-WAV via BFF'en (binær).
3. Operatøren opretter en version, kører kontroller og sender den gennem godkend og aktivér.
4. Ejeren ser stemmen med mærkerne "Pilot" og "Lyttetest afventer" samt bannerets "simuleret".
5. Ejeren klikker "Lyt" ("Afspiller simuleret lyd"), "Vælg som standard" og skriver egen tekst → "Generér og
   afspil", og gemmer udtaleordbogen (version 2).
6. **En ny browsersession viser samme standardstemme.**
7. Testsamtale med simuleret telefoni og simuleret motor: `assistant-request` giver `custom-voice`, og
   voice-request giver 200 med `x-simulated: 1` og PCM.

Screenshot: `web/test-results/**/v01-stemmer-*.png` (ikke committet). **Hele E2E-suiten: 48 bestået** (24 rejser × 2 viewports, 3,5 min).

## HTTP-kædetest (simuleret motor bag rigtig HTTP-grænse)

Opsætning:
- API med `TTS_ENGINE=http`;
- `tts_service` som separat proces (`uvicorn`, `TTS_ENGINE=fake`);
- `python -m voice_pipeline.eval.chain_smoke …`.

Resultatet er gemt i `evidence/chain-smoke-simulated-2026-09-27.json`:
- rights og normalization bestået, synthesis_smoke **simulated**;
- prøve-WAV 31.722 bytes;
- `assistant-request` gav `custom-voice`;
- voice-request 200 med første byte efter 68 ms og `x-simulated: 1`, så mærket bevares hen over
  HTTP-grænsen.

Latens (`evidence/bench-vapi-simulated-2026-09-27.json`, hardware: udviklingscontainer, **fake-motor, ingen
model**) måler kun rørføringens overhead:

| Samtidighed | Første lyd p50 / p95 | Samlet p50 / p95 |
|---|---|---|
| 1 | 62 / 72 ms | 114 / 153 ms |
| 4 | 282 / 379 ms | 387 / 630 ms |

Stigningen ved 4 samtidige skyldes, at tjenesten kører én generering ad gangen pr. model. Det er designet
sådan: stemmetilstanden er delt, og der skaleres med replikaer.

## GPU-måling på RunPod L4 (28/9 2026)

Rigtig syntese med Røst-v3 (revision `7ce205ce…`, ikke simuleret) på RunPod Secure Cloud L4 24 GB i EUR-IS-1.
Koden var commit `abdaf72`, og stemmen var modellens egen indbyggede `conds.pt`, ikke en CoRal-TTS-kandidat. Poden
kørte 19,5 min og kostede ca. $0,16 (0,33 t × $0,49). Klar til brug 4 min efter oprettelse, inkl. installation og
download af vægte. Resultater: `evidence/bench-tts-runpod-l4-2026-09-28.json` og
`evidence/testset-runpod-l4-2026-09-28.jsonl`.

| Måling | p50 | p95 |
|---|---|---|
| Syntese pr. enhed på serveren (`/metrics`, 122 kald) | 2.932 ms | 3.952 ms |
| RTF på serveren | 0,83 | 0,94 |
| `bench tts`, 1 samtidig (inkl. ca. 1 s RunPod-proxy) | 3.601 ms | 4.688 ms |
| `bench tts`, 2 samtidige | 5.957 ms | 7.246 ms |
| `bench tts`, 4 samtidige | 12.492 ms | 13.567 ms |
| Testsæt, første enhed (110 sætninger) | 3.054 ms | 4.839 ms |

**Konklusion:** L4 opfylder **ikke** målet om p95 < 1,5 s. Kun 1 af 110 sætninger havde første lyd under 1,5 s,
og selv uden proxy tager en enhed ca. 2,9 s på serveren. RTF ≈ 0,8 betyder, at hele svaret skal genereres, før
første byte sendes. Det kræver streaming-syntese, kortere første enhed eller hurtigere GPU, før L4 er brugbar til
telefoni. Ved 2 og 4 samtidige står kaldene i kø, fordi der er én model pr. GPU.

## Streaming-måling på RunPod RTX 4090 (28/9 2026)

Samme model, revision og stemme som L4-målingen. Koden er streaming-versionen (`tts_service/streaming.py`, commit
`835da35`):
- tokens bliver til lyd undervejs;
- token-trinnet afspilles som CUDA-graf;
- lyd laves i vinduer;
- 2 modelinstanser deles om én GPU.

Stream-indstillingerne var første bid efter 30 tokens, derefter hver 40., et vindue på 56 tokens, 75 tokens af
stemmeprøven og 5 CFM-trin. Den gamle endpoint (`/v1/synthesize`, hele sætningen) blev målt på samme GPU til
sammenligning. Resultater ligger i `evidence/bench-tts-stream-rtx4090-2026-09-28.json` og
`evidence/testset-stream-rtx4090-2026-09-28.jsonl`.

L4 og A5000 var udsolgt, så målingen er lavet på en RTX 4090 (Secure Cloud, $0,74/t). Den første pod, en Community
4090, havde en defekt GPU-vært ("CUDA unknown error") og blev slettet. Poderne kostede ca. $1,05 i alt.

| Testsæt, 110 sætninger, 1 ad gangen | p50 | p95 |
|---|---|---|
| **Streaming: første lyd på serveren** | **652 ms** | **661 ms** |
| Streaming: første lyd hos klienten (inkl. RunPod-proxy fra udviklingscontaineren) | 821 ms | 2.138 ms |
| Gammel: hel enhed på serveren | 2.509 ms | 3.900 ms |
| Streaming: RTF | 0,60 | 0,90 |
| Streaming: afspilningshul (ville opkalderen høre en pause?) | 0 s | 0 s |

- **110 af 110 sætninger** havde første lyd under 1,5 s på serveren. På L4 med den gamle version var det 1 af 110.
- **Samtidige opkald (streaming, 2 instanser):**
  - Ved 2 samtidige er første lyd p50 1,17 s og p95 1,34 s, med huller på op til 0,43 s.
  - Ved 4 samtidige står 2 i kø, og klientens første lyd er p95 8,6 s.
  - Én RTX 4090 klarer altså 1 samtale uden huller og 2 med små huller. Flere samtidige samtaler kræver flere GPU'er.
- **Hvor tiden går (en sætning på 130 tokens):** T3 bruger 13–14 ms pr. token med CUDA-graf mod 21 ms uden. En
  S3Gen-afkodning tager ca. 0,23 s med 5 CFM-trin og ca. 0,42 s med 10. Afkodningen er bundet af overhead, ikke af
  længden.
- **Ikke vurderet:** lydkvaliteten med 5 CFM-trin og den afkortede stemmeprøve. 10 sætninger ligger klar som
  gammel/ny-par til lytning. L4 er ikke målt med streaming, fordi den var udsolgt. L4 er langsommere end 4090, så
  tallene skal måles igen på den GPU, der vælges til drift.
- **Mislykket optimering:** `torch.compile` (inductor) crashede på poden. Derfor bruges en manuelt optaget CUDA-graf
  (`TTS_T3_GRAPH=cuda`), som ikke kræver compiler.

## Ikke bestået / ikke kørt (præcise blokeringer)

| Del | Status | Blokering |
|---|---|---|
| Import af CoRal-TTS (prøve og fuld) | **Ikke kørt** | `huggingface.co` afvises af miljøets egress-politik (403 på CONNECT) |
| Rigtig dansk syntese med Chatterbox Multilingual | **Ikke kørt** | Samme blokering for `ResembleAI/chatterbox`. Desuden ingen GPU i containeren (CPU er muligt, men for langsomt til telefoni) |
| Lydfiler for 110 testsætninger pr. kandidat | **Ikke genereret** | Afhænger af de to ovenstående. Værktøjet (`synthesize_testset`) er klar |
| Blind lyttetest (≥ 3 danske lyttere) | **Afventer** | Kræver rigtig lyd. Værktøjet (`listening_test build/score`) er klar. Ingen vurderinger er opfundet |
| Latens p50/p95 på GPU, koldstart, RTF | **Streaming bestået på RTX 4090; L4 kun målt uden streaming** | Streaming på 4090: første lyd p95 0,66 s, ingen huller ved 1 samtale. L4 uden streaming: p95 ≈ 4–5 s. Se de to afsnit ovenfor. Lydkvalitet ved 5 CFM-trin er ikke lyttevurderet |
| Rigtig testsamtale via Vapi med Dialogbot-stemme | **Ikke bestået** | Kræver TTS-host med rigtig model og en aktiv, godkendt stemme. Vapi-nummer og webhook findes allerede |
| Kategorisering (køn, dialekt, alder) af CoRal-TTS-indtalerne | **Ukendt** | Kræver gennemlytning. Registreret som ukendt |
