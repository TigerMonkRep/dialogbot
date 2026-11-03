# Dialogbots egen opkaldsmotor (uden Vapi)

Status 3. november 2026: bygget og testet med falske udbydere (`tests/test_callengine.py`). Ikke kørt mod de rigtige
udbydere endnu. **Ingen numre peger på motoren**; hovednummeret kører stadig på Vapi.

## Hvorfor

Med Vapi har to systemer en mening om, hvornår kalderen er færdig: genkenderen og Vapi. Den 3/11 var de uenige
(Soniox sendte kun final ved sit eget `<end>`, Vapi ventede på final), og Peter svarede aldrig. I motoren er
genkenderens `<end>` turen – én ejer. Desuden: dansk turtagning vi selv styrer, ingen Vapi-minutpris, og en optagelse
med to spor (venstre: kalder, højre: Peter) af hvert opkald.

## Kæden

```
Twilio Media Streams (8 kHz µ-law) → Soniox stt-rt-v5 (µ-law direkte, eget endpoint)
  → Claude (streamet, værktøjer, end_call) → ElevenLabs (én sætning ad gangen, ulaw_8000) → Twilio
```

Ingen lydkonvertering på vejen. Prompt, hilsen, viden, værktøjer, stemme og udtaleordbog hentes præcis som til Vapi
(`vapi.assistant_config`, `standard.provider_voice`, `actions.tools_for`). Opkaldet gemmes via samme
`vapi.end_of_call` (indbakke, leads, opfølgning uændret) med `calls.provider = 'dialogbot'`.

## Turtagning (`app/modules/callengine/engine.py`, tal i `Timing`)

- Kalderens tur slutter, når Soniox siger det. Peter svarer med det samme; første sætning går til stemmen, mens resten
  skrives.
- Afbrydelse: en partial med ≥ 2 ord, der ikke er "ja/mm/okay …", stopper Peter med det samme (Twilio `clear`).
  Historikken indeholder kun det, kalderen faktisk hørte.
- "Ja", "mm" mens Peter taler eller tænker: ignoreres.
- To kalder-ture før Peter når at sige noget: svares samlet.
- Stilhed: efter 12 s "Er du der stadig?", efter 12 s mere farvel og læg på. Højst 15 min.
- Peter lægger selv på med `end_call` eller en afslutningsfrase – efter lyden er spillet.

## Sådan testes den

1. **Simulator (ingen telefon ringer):** `POST /api/v1/operator/telephony/engine/simulate` med en WAV (`file`) eller
   `fixture=<navn>` fra `tests/fixtures/linden`. Optagelsen spiller kalderen, den rigtige motor svarer i realtid.
   Svar: tur-for-tur log med svartider + `recording` (to spor).
2. **Testopkald:** `POST /api/v1/operator/telephony/engine/test-call {"to": "+45…"}` – Peter ringer op fra
   hovednummeret og kører på motoren. Hovednummerets indgående opkald røres ikke. Gemmes uden lead.
   Optagelse: `GET …/engine/calls/{CallSid}/recording.wav`.
3. **Flyt et nummer (først når godkendt):** `POST …/engine/numbers/{id}/inbound {"confirm": true}`.
   Tilbage til Vapi: `POST /api/v1/operator/telephony/numbers/{id}/inbound`.

Indstillinger: `ENGINE_MODEL` (standard: `VAPI_MODEL`/Haiku 4.5), `ENGINE_SONIOX_ENDPOINT_JSON`. Nøgler:
`SONIOX_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `VAPI_SERVER_SECRET` (signerer stream-tokens).

## Mangler (ærligt)

- Ikke kørt mod de rigtige udbydere; svartid og Soniox' endpoint på telefonlyd er ikke målt.
- Dialogbots egne stemmer (custom-voice) – motoren bruger nummerets/standardens ElevenLabs-stemme.
- Udgående kampagner, salgskanalens værktøjer, viderestilling til menneske, telefonsvarer-genkendelse.
- Baggrundslyd ("office").
