# Stemmetest: dansk talegenkendelse, målt på samme lyd

Status 3. november 2026. **Der er ingen målinger mod de rigtige udbydere endnu** – sessionen havde hverken `SPEECHMATICS_API_KEY`, `SONIOX_API_KEY` eller `ELEVENLABS_API_KEY`, og der findes ingen menneskeindtalte optagelser. Alt nedenfor, der kan bygges uden dem, er bygget og testet (mock og rigtig lokal WebSocket); resten står som *mangler*. Der er hverken opfundet tal eller udpeget en vinder.

## Hvor du åbner den

*Operatør → Værktøjer → Stemmetest* (`/app/operator/stemmetest`, kun Dialogbot-operatører; API `/api/v1/operator/stemmetest`). Siden viser testtilstand, valgt virksomhed, aktive profiler og status; profiler uden adgang står som *Mangler adgang* med den manglende miljøvariabel; profil A og B står som *Måles i live-opkald*. Resultater har etiketterne *Forstod kunden / Bookede korrekt / Afbrydelser / Svartid / Stemme / Pris*; model, endpointing, lydformat, SDK-versioner og eventtidslinje ligger under *Avanceret*.

Uden browser:

```bash
python -m app.modules.stt.cli                          # alle profiler med nøgle × alle cases med lyd
python -m app.modules.stt.cli --profile E --profile F --case S03 --mode natural --out run.json
RUN_LIVE_STT=1 pytest tests/test_stemmetest_live.py -s # rigtig forbindelse, kun med nøgler
pytest tests/test_stemmetest.py                        # mock + lokal WebSocket, ingen nøgler
```

## Fund i den eksisterende løsning (verificeret i koden)

- Telefonen kører **Vapi**; standardgenkenderen er Deepgram Nova-3 dansk med Nova-2 som reserve (`app/modules/telephony/vapi.py:45`, `transcriber_for`). Vapi ejer taleturen (`startSpeakingPlan`, tempoindstillinger i `PACING`, se `docs/telephony/samtaletempo.md`).
- Speechmatics findes to steder: Vapis indbyggede integration (`VAPI_TRANSCRIBER_JSON={"provider":"speechmatics","language":"da"}`, med navneordbog fra `danish_names.py`) og **egen bro til Agent STT/Linden** (`app/modules/telephony/linden.py`, Vapi *custom transcriber* → `/api/v1/webhooks/vapi/transcriber`). Broen sender kun kundens kanal, kun delvis/endelig tekst; Vapi lukker turen.
- Stemmen er Vapi-udbyderen `11labs` med `voiceId` og `voice_model` pr. telefonnummer (`vapi.py:429`). Modellen `eleven_v4_turbo` er den dokumenterede (`samtaletempo.md`) og står i `VOICE_MODELS`; hvilken model Peters nummer **faktisk** har i databasen er ikke læst (ingen driftsdata rørt) og skal ses under Indstillinger → Telefoni.
- Repoets egen måling fra 2. november (20 danske navne over telefon): Deepgram 5, Azure 8, ElevenLabs Scribe 9 rigtige (`samtaletempo.md`). Det er den observation, der udløste Speechmatics-sporet – ikke en måling af denne opgave.
- Der findes **ingen browser-talekanal** (ingen Vapi Web SDK/public key i `web/`). Browsersamtalen er derfor *ikke bygget*; siden siger det.

## Arkitektur: én runtime, ingen ny platform

Alle profiler bruger den eksisterende samtalerutine (Vapi: LLM, instruktioner, kundekontekst, booking-tools, telefoni, Peters stemme). Den eksisterende egen integration – broen – kan bære flere genkendere, så **LiveKit/Pipecat er ikke indført** (tillægget forbyder flere frameworks, hvor en egnet integration findes). Broen vælger genkender med `stt` (`VAPI_TRANSCRIBER_JSON={"provider":"custom-transcriber","stt":"soniox"}`, eller pr. virksomhed `VAPI_STT_BY_WORKSPACE_JSON`). Uden genkenderens nøgle forbliver opkaldet på produktionsruten.

Direkte genkendelse på afspillet lyd kører gennem de samme adaptere (`app/modules/stt/adapters.py`): Speechmatics Realtime, Speechmatics Agent STT, Soniox, ElevenLabs Scribe – hver med en ren `handle(besked)`, der oversætter udbyderens egne beskeder til ét fælles eventsprog (`events.py`). Rå udbyderbeskeder bevares på hvert event.

| Profil | Hvad | Model (anmodet) | Hvem lukker taleturen |
|---|---|---|---|
| A | Nuværende (Deepgram via Vapi) | nova-3 | Vapi |
| B | Vapi + Speechmatics (native) | ukendt, Vapi vælger | Vapi |
| C | Direkte Realtime, model eksplicit | `enhanced` | Speechmatics `EndOfUtterance` / replay (`ForceEndOfUtterance`) |
| D | Direkte Agent STT | `linden-1` | Speechmatics VAD `EndOfTurn` / replay (`external`) |
| E | Direkte Soniox | `stt-rt-v5` | Soniox `<end>` / replay (`finalize` → `<fin>`) |
| F | Direkte ElevenLabs STT | `scribe_v2_realtime` | lokal regel (VAD-commit) / replay (manuel commit) |

**C+ er ikke en separat profil:** C sender allerede `enhanced` eksplicit med samme opsætning (SDK'ens standard er desuden `enhanced`), så C+ ville være en dobbeltkørsel. Det anmodede og det af udbyderen rapporterede modelnavn gemmes i hver kørsel; hvor udbyderen intet rapporterer (Speechmatics, Soniox), står den bagvedliggende version som *ukendt*.

Præcis én komponent ejer taleturen. I live-opkald er det Vapi (broen videresender aldrig `turn_ended`); i replay er det enten replayet (kontrolleret) eller udbyderen (naturlig). Soniox' `<end>`/`<fin>` er kontroltokens og kommer aldrig i kundens tekst; en ElevenLabs-*commit* er ikke bevis for afsluttet tanke og giver aldrig en taletur alene.

## Kontrolleret STT-test eller naturlig afslutning

- **Kontrolleret** (standard): replayet lukker turen ved optagelsens kendte slutning (+ 200 ms stilhed). Det isolerer *genkendelse* og er en kontrolleret STT-test – ikke dokumentation for en naturlig samtale.
- **Naturlig**: udbyderens endpointing afgør efter lyd + 1,5 s stilhed. Forskelle vises som `turn_count`/`premature_split`/`closed_by` og tilskrives aldrig genkendelsesmodellen.

Lyd afspilles i realtid (100 ms-pakker, tempo mod vægur, backpressure fra forbindelsen). Alle tider er målt på ét vægur fra sidste afleverede lydpakke. Batchtransskription tæller ikke.

## Verificerede forhold og afvigelser (kontrolleret 3. nov. 2026)

| Emne | Kilde | Resultat |
|---|---|---|
| Speechmatics Agent STT | installeret `speechmatics-agent-stt` 0.3.0, `speechmatics-rt` 1.2.2 | Model `linden-1`; `/v2/agent`; `TurnConfig` (`vad`/`external`) ligger *ved siden af* transskriptionsconfig; `ForceEndOfUtterance` med tidsstempel; `max_delay` m.fl. afvises (`linden.py`). |
| Speechmatics Realtime | samme SDK | `Model`: `enhanced`, `standard`, **`melia-1`, `oak-1`** findes også i SDK'en – ikke afprøvet, ikke i nogen profil. |
| Speechmatics region | SDK-kode | Standard-URL i SDK'en er `wss://eu2.rt.speechmatics.com/v2` (tillæggets eksempel nævner `eu.`); projektets krav styres med `SPEECHMATICS_RT_URL`. Nærmeste globale endpoint er ikke en fast EU-region. |
| Soniox | docs.soniox.com (websocket-api, endpoint-detection, manual-finalization, models) | `wss://stt-rt.soniox.com/transcribe-websocket`; nøgle i `Authorization: Bearer` (`api_key` i start-beskeden er **udfaset**, afvises fra 15/1 2027); start-JSON, derefter binær lyd; `{"type":"finalize"}` → `<fin>`; endpoint-detektion → `<end>`; **tom tekstramme** afslutter strømmen (tom binær ramme er tom lyd); `stt-rt-v4` er alias for `stt-rt-v5`; aggressiv endpointing kan koste nøjagtighed. |
| ElevenLabs STT | elevenlabs.io/docs (speech-to-text realtime) | `wss://api.elevenlabs.io/v1/speech-to-text/realtime`, `model_id=scribe_v2_realtime`, `xi-api-key`, `audio_format` (bl.a. `pcm_8000`, `pcm_16000`, `ulaw_8000`), `commit_strategy` = `manual`/`vad`/**`turn_prediction`** (ikke brugt), `keyterms` højst 50 (+20 % pris), `transcript_edit`/`entity_detection` bruges aldrig, så rå tekst scores. |
| Vapi | repoets eksisterende integration; Vapis side ikke genlæst | Vapi eksponerer ikke den bagvedliggende Speechmatics-model; der er **ikke** sat udokumenterede felter i nogen Vapi-konfiguration. |

Lokale tests dækker beskedformaterne (håndskrevne i de dokumenterede formater) og den rigtige WebSocket-transport mod en lokal falsk server (headers, startbesked, binær lyd, finalize, tom tekstramme, base64-chunks, commit). Ingen af delene er et bevis for, hvordan en udbyder klarer dansk.

## Målinger – hvad der er implementeret

| Mål | Status |
|---|---|
| Ordfejl (WER, rå tekst, dansk normalisering) | Implementeret pr. kørsel og samlet (fejl/ord vises) |
| Vigtige oplysninger (navn, nummer, dato, tid, antal, sted) | Implementeret, hits/total pr. type; forkert ciffer eller tid er en miss |
| For tidligt svar | Kun som `premature_split` i replay (udbyderen delte én udtalelse); ægte mål kræver samtale |
| Svartid | Kun *STT-delen* (første tekst, endelig tekst og slut på taletur efter sidste lydpakke; median + p95 + n, flaget som usikker under 20). Første hørbare agentsvar er **ikke** målt |
| Falske afbrydelser / reaktion på afbrydelse | **Ikke målt** – kræver live-samtale (cases K31–K35 og SC05–SC07 er forberedt) |
| Opgaveløsning/booking | Ikke målt her. Bookingidempotens og kundeadskillelse er dækket af de eksisterende tests (`test_bookings.py`, `test_identity_and_access.py`) |
| Stabilitet | Fejl og afbrudte forbindelser registreres pr. kørsel (`fejl`/`mangler_adgang`) |
| Pris | Lydsekunder registreres; kroner/dollars kun med egen prisliste (`STEMMETEST_PRICES_JSON`), ellers *pris ikke angivet* |

Ingen sammenlagt kvalitetsscore – skjulte vægte kunne skjule et forkert telefonnummer bag et hurtigt svar.

## Testgrundlag

`tests/fixtures/stemmetest/manifest.json`: 40 korte cases (37 menneskeindtalte afventer + 3 kendte syntetiske Peter-optagelser), 14 `tuning` og 26 `final` (adskilt), 10 samtalescenarier, tidszone Europe/Copenhagen, reference = ordene der siges, forventede nøgleoplysninger pr. case. **Kun 3 cases har lyd i dag, og de er syntetiske** – dialekt, støj og telefonkvalitet er uafklaret. Hvad der skal indtales: [`stemmetest-optagelser.md`](stemmetest-optagelser.md). Den fælles ordliste (firmanavne + de mest almindelige danske navne) indeholder ingen testsvar (testet), og hver udbyders grænse registreres (ElevenLabs: 50 keyterms, derfor står firmaordene først).

## Stemmen (TTS) – separat fase

Arbejdet er forberedt, ikke kørt. T0 (nuværende) og T1 (ElevenLabs v4 Turbo) er sandsynligvis **den samme model**: koden og dokumentationen bruger allerede `eleven_v4_turbo` (se ovenfor); en T1 findes kun som ændring, hvis Peters nummer står på en anden model. Derfor er T2 den relevante sammenligning (fx `eleven_flash_v2_5`, som `samtaletempo.md` nævner som hurtigere men fladere). `scripts/stemmetest_tts_samples.py` laver blinde prøver (Gastro Hall, Racehall, Aarhus, Højbjerg, »halv syv«, testnummer, bookingbekræftelse) med skjult etikettering og `key.json`; Peters voice id skal gives af dig og gættes aldrig. Samme voice id med anden model er et modelskifte; anden stemme er både stemme- og modelskifte. Der er ikke oprettet en stemmeklon, og ingen prøver er genereret (ingen nøgle).

## Anbefaling (så ærlig som datagrundlaget tillader)

**Ingen genkender kan udpeges som bedst blandt de afprøvede profiler – der er ikke afprøvet nogen mod rigtig tale.** Den mindst komplicerede vej, der opfylder kravene, er at blive på Vapi med broen som eneste ekstra komponent og først skifte, når målingerne viser en forskel på kritiske oplysninger (navne, tal, tider). Næste konkrete skridt:

1. Sæt `SPEECHMATICS_API_KEY`, `SONIOX_API_KEY`, `ELEVENLABS_API_KEY` på staging og kør `RUN_LIVE_STT=1 pytest tests/test_stemmetest_live.py -s` (bekræfter forbindelse og modelnavne).
2. Indtal K-sagerne efter `stemmetest-optagelser.md` (mindst tre talere, helst telefon), kør kontrolleret på `tuning`, vælg højst tre indstillingsvarianter pr. profil, og mål `final` én gang.
3. Prøv de to-tre bedste som rigtige opkald på staging (`VAPI_STT_BY_WORKSPACE_JSON`) og mål afbrydelser, første hørbare svar og booking med mennesker, som svarer på agentens spørgsmål (SC01–SC10).
4. Skift først produktion for en enkelt virksomhed, når kritiske oplysninger er bedre *og* stabiliteten holder.

**Nyt driftsansvar ved at forlade Vapis egen genkender:** broen er vores tjeneste (WebSocket-forbindelser pr. opkald, nøgler, kvoter, reconnects), udbyderen har egen tilgængelighed, og lydformat/kanalforskydning skal overvåges (`linden.levels` logges). Kun hvis målingerne viser, at *taleturstyring* (ikke genkendelse) er flaskehalsen, bør en agentramme (LiveKit/Pipecat) overvejes – det er ikke vist.

## Aktivering og tilbageførsel pr. virksomhed

`VAPI_STT_BY_WORKSPACE_JSON={"<arbejdsrums-uuid>": "soniox"}` ændrer kun den virksomheds opkald; fjern posten og genstart for at gå tilbage. Mangler nøglen, forbliver opkaldet på Deepgram. Intet flyttes automatisk, og Stemmetest-siden flytter aldrig kundeopkald (alle kørsler er replay).

## Kendte begrænsninger

- Ingen rigtige udbyderkørsler, ingen menneskeindtalte optagelser, ingen browsersamtale, ingen automatisk måling af afbrydelser/første hørbare svar.
- Udbydernes regions- og dataopbevaringskrav for Soniox og ElevenLabs er ikke undersøgt (markeret *ikke testet*); testoptagelser forlader serveren til udbyderen – tjek mod projektets krav, før der bruges rigtige kunders lyd.
- Uploadede optagelser gemmes ikke (kun resultatet); kørsler gemmes i `stt_test_runs` (operatør-only, ingen nøgler).
