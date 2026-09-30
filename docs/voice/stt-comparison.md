# Tale-til-tekst i telefonen: Deepgram, Azure eller CoRal?

Telefonen bruger i dag **Deepgram Nova-3, dansk** via Vapi (`app/modules/telephony/vapi.py`, `DEFAULT_TRANSCRIBER`).
Siden 30/9 2026 får den også en **ordliste** (`keyterm`) fra arbejdsrummets godkendte viden: firmanavn, ydelser,
tilbud, bookingtyper og steder. Det er højst 50 ord (Deepgram anbefaler 20–50). Uden godkendt viden sendes ingen
ordliste, og en transskriber sat i `VAPI_TRANSCRIBER_JSON` med egen `keyterm` bliver ikke ændret.

## Sådan måles det

`python -m voice_pipeline.eval.stt_compare` sender det samme lydklip gennem hver motor. Klippet er først gjort
telefonagtigt: 8 kHz, 300–3400 Hz og G.711 μ-law. Scriptet måler:

- **WER og CER** efter samme danske normalisering som i opkaldene;
- **"tal og navne fanget"**: cifre og navne fra referenceteksten, som også står i transskriptionen;
- **median svartid** pr. klip (for-optaget lyd, ikke streaming – kun til sammenligning mellem motorer).

| Datasæt | Hvad det er | Adgang |
|---|---|---|
| `fleurs` | Google FLEURS da_dk test, rigtig oplæst tale | Åben (CC-BY-4.0) |
| `coral` | CoRal read_aloud test, rigtige danskere inkl. dialekter | Kræver `HF_TOKEN` og accepterede vilkår |
| `testset` | Vores 110 receptionistsætninger (`voice_pipeline/eval/testset_da.jsonl`) | Kræver lyd; her Røst-syntese (syntetisk) |
| `dir:PATH` | Egne optagelser (`*.wav` + `*.txt`) | Rigtige opkald er den bedste test |

## Resultater indtil nu

| Motor | Datasæt | Klip | WER | CER | Tal og navne fanget | Median ms (CPU) |
|---|---|---|---|---|---|---|
| CoRal `roest-v3-wav2vec2-315m` | FLEURS, telefonlinje | 40 | 23,4 % | 7,0 % | 9/23 | 683 |
| CoRal `roest-v3-wav2vec2-315m` | Testsæt (syntetisk Røst-stemme), telefonlinje | 40 | 18,7 % | 5,9 % | 18/31 | 285 |

Bevis: `docs/voice/evidence/stt-coral-wav2vec2-phone-2026-09-30.json`.

- **Deepgram og Azure er ikke målt endnu.** Det kræver `DEEPGRAM_API_KEY` samt `AZURE_SPEECH_KEY` og
  `AZURE_SPEECH_REGION` i miljøet. Der er ikke opfundet tal.
- **CoRal Whisper 1.5B er ikke målt.** Den kræver en GPU.
- Testsættets lyd er syntetisk (én stemme, ren udtale) og er derfor for let. FLEURS er rigtig tale, men oplæst
  Wikipedia-tekst, ikke telefonsamtaler.
- Typiske fejl hos CoRal på telefonlyd: "AI-assistent" → "ejeassistent", "Hvilken adresse" → "midten af dresse".
  Det er netop korte, vigtige ord.

## Næste skridt

1. Kør med nøglerne:

   ```
   python -m voice_pipeline.eval.stt_compare --dataset fleurs:100 --dataset testset:110 \
       --testset-audio <klip> --engine deepgram --engine azure --engine coral \
       --keyterms keyterms.txt --out eval-runs/stt.json
   ```

2. Tilføj `coral:100`, når `HF_TOKEN` er sat. Det giver dialekter.
3. Den endelige test: 20–30 rigtige prøveopkald, optaget med samtykke, med navne, adresser og telefonnumre.
