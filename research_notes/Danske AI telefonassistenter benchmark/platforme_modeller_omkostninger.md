# Teknologiplatforme, modeller og omkostningsstruktur bag danske AI-telefonassistenter (status: september 2026)

**Valutaforudsætninger (brugt i hele dokumentet):**
- USD/DKK = 6,57 (evaluta.dk, 28. september 2026: "1 USD = 6.5699 DKK") — [Kilde](https://www.evaluta.dk/en/us-dollar-exchange-rate). Nationalbankens indikative kurs 23. sept. 2026 var 6,5512 — [Kilde](https://www.exchangerates.org.uk/USD-DKK-spot-exchange-rates-history-2026.html).
- EUR/DKK ≈ 7,46 (dansk fastkurspolitik; **antagelse, ikke hentet fra kilde i denne research**).
- SEK/DKK ≈ 0,65, NOK/DKK ≈ 0,63, GBP/DKK ≈ 8,5 (**grove antagelser, ikke verificeret** — brug kun til størrelsesordener).
- Alle priser er dateret med den dato, kilden blev hentet/publiceret. Priser markeret "hentet 29-09-2026" er læst direkte fra leverandørens prisside den dag.

---

## 1. Orkestreringsplatforme: listepriser, dansk sprogunderstøttelse og EU-datalokation

### Takeaway
Orkestreringslaget koster typisk 0,05–0,09 USD/min (0,33–0,59 kr/min) alene, og først når STT, LLM, TTS og telefoni lægges oveni, lander man på ca. 0,09–0,20 USD/min (0,6–1,3 kr/min). Kun ElevenLabs dokumenterer en EU-datalokationsmulighed (enterprise); Vapi og Retell offentliggør ingen EU-residency. Bland er den eneste med "alt inkluderet"-pris pr. minut.

### Cited Findings

**Vapi (hentet 29-09-2026 fra prissiden)**
- Platformgebyr "$0.05/min Vapi hosting" ved forbrugsbaseret plan; Pro-pakke: "10% of Vapi hosting fee" med "$999/mo minimum" — [Vapi pricing](https://vapi.ai/pricing)
- Inkluderet samtidighed: 4 (ingen pakke), 10 (Core), 30 (Pro); ekstra linjer "$10 / line / month" — [Vapi pricing](https://vapi.ai/pricing)
- Telefonitransport pr. minut: Vapi Telephony/SIP: gratis; Twilio inbound $0.008/min; Twilio outbound $0.014/min; Vonage $0.00814/min; Telnyx $0.0055/min — [Vapi pricing](https://vapi.ai/pricing)
- Pass-through uden markup (som vist på prissiden): Deepgram "$0.0095 - $0.0099/min"; OpenAI "$0.0077 - $0.0452/min"; ElevenLabs "$0.0146 - $0.0238/min" — [Vapi pricing](https://vapi.ai/pricing)
- EU-datalokation nævnes ikke på prissiden — [Vapi pricing](https://vapi.ai/pricing); en europæisk købsguide (26. juli 2026) konkluderer, at Vapi ikke publicerer EU-residency, og at svaret "must come from sales team in writing" — [30Elevate](https://30elevate.com/en/blog/ai-voice-agent-platforms/)
- Uafhængige analyser (2026) anslår realistisk all-in for Vapi-stakke til ca. $0.07–$0.25/min, over $0.30 med premium-stemmer og store modeller — [Layer3Labs](https://www.layer3labs.io/guides/vapi-pricing); [CloudTalk](https://www.cloudtalk.io/blog/vapi-ai-pricing/)
- Vapi dokumenterer per-udbyder sprogloft: Deepgram 100+, Google STT 125+, Gladia 110+, Azure TTS 140+ sprog; dansk skal bekræftes pr. valgt udbyder — [Vapi multilingual docs](https://docs.vapi.ai/customization/multilingual); [ThunderPhone sammenligning](https://thunderphone.com/compare/voice-ai-language-support)

**Retell AI (hentet 29-09-2026 fra prissiden)**
- "Retell Voice Infrastructure": "$0.055/minute"; "Retell Platform Voices": "$0.015/minute"; ElevenLabs-stemmer "$0.040/minute"; Cartesia "$0.015/minute"; Minimax/Fish/OpenAI/Inworld "$0.015/minute" — [Retell pricing](https://www.retellai.com/pricing)
- LLM pr. minut (standard tier, som vist på siden): GPT 4.1 $0.045; GPT 5.4 $0.080; GPT 5.5 $0.16; "GPT 5.6 Terra" $0.064; "GPT 6 Astra" $0.32; "Claude 5 Sonnet" $0.064; Claude 4.6 Sonnet $0.08; Claude 4.5 Haiku $0.025; Gemini 3.5 Flash $0.048; Gemini 3.0 Flash $0.016 — [Retell pricing](https://www.retellai.com/pricing)
- Telefoni (US/Twilio) "$0.015/min"; telefonnummer "$2.00/month"; verificeret nummer "$10.00/phone/month"; samtidighed "Free for first 20", derefter "$8/call/month" — [Retell pricing](https://www.retellai.com/pricing)
- Ingen EU-datalokation nævnt på prissiden — [Retell pricing](https://www.retellai.com/pricing); 30Elevate (26-07-2026): data "primarily stored and processed" i USA, EØS-overførsler via Standard Contractual Clauses — [30Elevate](https://30elevate.com/en/blog/ai-voice-agent-platforms/)
- Uafhængige analyser: produktion typisk $0.13–$0.15/min; med Claude 4.5 Sonnet + ElevenLabs + Retell-telefoni ca. $0.19/min — [Cekura](https://www.cekura.ai/blogs/retell-ai-pricing-per-minute); [11x](https://www.11x.ai/guides/retell-ai-pricing)

**Bland AI (hentet 29-09-2026 fra prissiden)**
- Start: "$0.14/min" taletid, "$0.05/min" overførselstid, $0 platformgebyr, 100 opkald/dag, 10 samtidige; Build: "$0.12/min", "$299/month platform fee", 2.000 opkald/dag, 50 samtidige; Enterprise: custom, "data residency" nævnes — [Bland pricing](https://www.bland.ai/pricing)
- Prisen inkluderer LLM ("No token charges"), realtidstransskription og TTS — [Bland pricing](https://www.bland.ai/pricing)
- Bland gik i december 2025 fra universel $0.09/min til tiered struktur; Scale-tier $0.11/min for $499/md rapporteres — [PxlPeak](https://pxlpeak.com/blog/ai-tools/bland-ai-pricing); [CloudTalk](https://www.cloudtalk.io/blog/bland-ai-pricing/)

**ElevenLabs Agents / ElevenAgents (hentet 29-09-2026 fra prissiden)**
- Planer: Free $0 (15 min), Starter $6 (75 min), Creator $22 (275 min), Pro $99 (1.238 min), Scale $299 (3.738 min), Business $990 (12.375 min), Enterprise custom — [ElevenAgents pricing](https://elevenlabs.io/pricing/agents)
- Ekstra minutter "$0.08 per minute"; "burst pricing $0.16 per minute" over samtidighedsgrænsen; SMS "$0.003 each"; samtidighed 4/6/10/20/30/40 — [ElevenAgents pricing](https://elevenlabs.io/pricing/agents)
- LLM "billed separately"; telefoni "included on every plan" (eksterne udbydere fakturerer direkte) — [ElevenAgents pricing](https://elevenlabs.io/pricing/agents)
- Prisen blev sænket fra $0.10 til $0.08/min (20 %) — [ElevenLabs blog](https://elevenlabs.io/blog/weve-lowered-api-agents-pricing-and-introduced-pay-as-you-go)
- EU-datalokation: "Enterprise feature"; dækker *lagring* i EU, men "processing may nevertheless occur outside of the selected location, including by ElevenLabs' international affiliates and subprocessors"; processering kan begrænses til EU via "Zero Retention Mode and the API" — [ElevenLabs data residency docs](https://elevenlabs.io/docs/overview/administration/data-residency); [ElevenLabs blog: European Data Residency](https://elevenlabs.io/blog/introducing-european-data-residency)
- Dansk er understøttet i ElevenAgents (via Flash v2.5/v3-modellerne, se afsnit 2) — [ElevenLabs help: languages in Eleven Agents](https://elevenlabs.io/docs/help-center/product/eleven-agents/which-languages-can-i-use-with-eleven-agents)

**Synthflow (2026)**
- Pay-as-you-go: voice engine $0.09/min; LLM $0.02–$0.05/min; Synthflow-managed Twilio $0.02/min; BYO Twilio $0.00; typisk all-in $0.15–$0.24/min; ekstra samtidighed $20/slot/md (5 inkl.); nummer $1.50/md; white-label $2.000/md; Enterprise fra $30.000/år med volumenrater ned mod ~$0.07/min; de gamle $29–$449-abonnementer er udfaset — [Layer3Labs](https://www.layer3labs.io/guides/synthflow-pricing); [Quiq](https://quiq.com/blog/synthflow-pricing/); [Zeeg](https://zeeg.me/en/blog/post/synthflow-ai-pricing)

**LiveKit Agents / Pipecat Cloud (Daily)**
- LiveKit Cloud: $0.01/min pr. samtidig agent (hosting, dataoverførsel, observability inkl.); inferens købes separat, typisk $0.03–$0.07/min — [Telnyx om LiveKit](https://telnyx.com/resources/livekit-pricing-scale-voice-ai-costs); [LiveKit pricing](https://livekit.com/pricing)
- Pipecat Cloud: "$0.01 per running agent"-minut; reserved instance = 1/20 af aktiv instans — [Daily Pipecat Cloud pricing](https://www.daily.co/pricing/pipecat-cloud/)

**OpenAI Realtime API (hentet 29-09-2026 fra OpenAI's prisside)**
- gpt-realtime-2.1: audio "$32.00" input / "$64.00" output pr. 1M tokens; gpt-realtime-2.1-mini: "$10.00"/"$20.00"; gpt-audio-1.5 $32/$64; gpt-audio-mini $10/$20 — [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- Omregnet: ~600 audio-tokens pr. minut input, ~1.200 pr. minut output ⇒ ca. $0.05/samtaleminut på fuld model og ~$0.016 på mini (før kontekstvækst, efter caching); cached audio input $0.40 vs. $32 — [Layer3Labs](https://www.layer3labs.io/guides/openai-realtime-api-pricing); [HackerNoon måling af 4.000 sessioner](https://hackernoon.com/openai-realtime-api-pricing-in-2026-real-world-data-from-4000-measured-sessions)

**Twilio ConversationRelay / Telnyx Voice AI**
- ConversationRelay: ca. $0.07/min oveni almindelig taletakst — [Twilio Conversational AI pricing](https://www.twilio.com/en-us/products/conversational-ai/pricing); [30Elevate](https://30elevate.com/en/blog/ai-voice-agent-platforms/)
- Telnyx bundled Voice AI: $0.05/min basis; almindelige opkald $0.002/min ind/ud + SIP-trunking — [Telnyx vs Twilio](https://telnyx.com/resources/telnyx-vs-twilio-which-voice-api-is-better); [Optimize Smart](https://optimizesmart.com/blog/twilio-or-telynx-phone-numbers-for-voice-ai-agents/)

**Samlet "true cost"-tabel (Famulor, 3. april 2026, antager ElevenLabs $0.05–0.08/min, GPT-4o $0.01–0.03/min, Deepgram $0.01/min, 3,5 min pr. opkald):** Bland $0.10–0.18; Vapi $0.12–0.25; Retell $0.13–0.24; Synthflow $0.15–0.27 — [Famulor](https://www.famulor.io/blog/ai-voice-agent-pricing-2026-what-10-platforms-actually-cost-per-minute)

### Inferences
- Omregnet til DKK (6,57): Vapi-platformgebyr ≈ 0,33 kr/min; Retell voice infra ≈ 0,36 kr/min; ElevenAgents ≈ 0,53 kr/min; Synthflow voice engine ≈ 0,59 kr/min; Bland all-in 0,72–0,92 kr/min.
- Ingen af de store amerikanske orkestreringsplatforme (Vapi, Retell, Bland, Synthflow) kan i dag dokumentere EU-only *processering* på standardplaner; kun ElevenLabs (enterprise + ZRM) og selvhostede stakke (LiveKit/Pipecat på EU-servere) gør det muligt. Det er formentlig derfor, danske udbydere fremhæver "EU-servere" som differentiator (se afsnit 8).
- Retells LLM-liste viser, at de dyreste frontier-modeller (op til $0.32/min) alene kan koste mere end hele resten af stakken; danske udbydere med 1–2 kr/min overtakst må derfor køre på mellemstore modeller (Haiku/Flash/mini-klassen).

### Gaps
- Vapi/Retell/Bland/Synthflow offentliggør ikke en eksplicit "dansk understøttet"-liste på platformniveau; dansk afhænger af den valgte STT/TTS-udbyder. Ikke verificeret direkte i deres sprogdokumentation.
- Voiceflow's per-minut voice-priser er ikke undersøgt.
- Retell-prissidens modelnavne ("GPT 5.6 Terra", "GPT 6 Astra") er gengivet som vist på siden ved hentning; de kunne ikke krydstjekkes mod OpenAI's egen modelliste inden for denne research.

---

## 2. TTS med dansk: modeller, priser, kvalitet og latenstid

### Takeaway
ElevenLabs (Flash v2.5, v3, v4), Azure Neural TTS, Google Chirp 3 HD, Cartesia Sonic 3.x og Chatterbox Multilingual understøtter alle dansk; Deepgram Aura-2 gør **ikke**. Den bedste åbne danske TTS er CoRal-projektets Røst-v3 (Chatterbox-finetunes, MOS 4,23 hos danske lyttere). Prisen for TTS ligger på ca. $0.011–0.08 pr. 1.000 tegn hos ElevenLabs og $16–22 pr. 1M tegn hos Azure.

### Cited Findings

**ElevenLabs (hentet 29-09-2026)**
- Flash v2.5 understøtter 32 sprog inkl. dansk, ~75 ms modellatens, "sub-500ms end-to-end", anbefalet til realtids-agenter; Eleven v3 understøtter 74 sprog inkl. dansk ("dan") men med 5.000 tegns grænse pr. request (vs. 40.000 for Flash/Turbo) — [ElevenLabs models docs](https://elevenlabs.io/docs/overview/models); [ElevenLabs help: languages](https://help.elevenlabs.io/hc/en-us/articles/13313366263441-What-languages-do-you-support); [Deepgram om ElevenLabs sprog](https://deepgram.com/learn/elevenlabs-languages-vs-accents-support)
- PAYG API-priser: v4 "$0.022" pr. 1K tegn (72 % rabat til 12. okt.; normalpris $0.08); v4 Turbo "$0.011" pr. 1K (normalpris $0.04); v3 $0.08 pr. 1K; v3 Conversational $0.04 pr. 1K; Flash/Turbo $0.04 pr. 1K — [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- Abonnementer: Starter $6, Creator $22, Pro $99, Scale $299, Business $990 — [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- Vapi's pass-through for ElevenLabs i en agent-kontekst: "$0.0146 - $0.0238/min" — [Vapi pricing](https://vapi.ai/pricing)

**Azure Speech (Microsoft)**
- Neural TTS "$16 per 1 million characters"; Neural HD "$22 per 1 million characters" (nedsat fra $30 i marts 2026); gratis 500.000 tegn/md; commitment-tiers op til 53 % rabat ved ≥80M tegn/md — [Azure Speech pricing](https://azure.microsoft.com/en-us/pricing/details/speech/); [TextToLab](https://texttolab.com/blog/azure-text-to-speech-pricing); [Microsoft Tech Community: Neural HD voice updates](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/azure-speech-%E2%80%93-neural-hd-text-to-speech-recent-voice-updates/4505380)

**Google Cloud TTS**
- Chirp 3: HD understøtter "Danish (Denmark) – da-DK" samt fi-FI, nb-NO, sv-SE — [Google Chirp 3 HD docs](https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd)

**Cartesia**
- Sonic 3.6 taler 44 sprog inkl. dansk — [Cartesia languages](https://www.cartesia.ai/languages); [Cartesia Sonic 3.6 docs](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest)
- Planer Free $0 / Pro $5 / Startup $49 / Scale $299 / Enterprise; 1 credit pr. tegn; rapporteret ~$46.70 pr. 1M tegn — [CloudTalk Cartesia pricing](https://www.cloudtalk.io/blog/cartesia-pricing/); [eesel](https://www.eesel.ai/blog/cartesia-sonic-3-pricing)
- Retell fakturerer Cartesia-stemmer til $0.015/min vs. ElevenLabs $0.040/min — [Retell pricing](https://www.retellai.com/pricing)

**OpenAI TTS (hentet 29-09-2026)**
- tts-1 "$15.00 / 1M characters"; tts-1-hd "$30.00 / 1M characters"; gpt-4o-mini-tts "$12.00" pr. 1M output-audio-tokens — [OpenAI pricing](https://developers.openai.com/api/docs/pricing)

**Deepgram Aura-2**
- Understøtter 7 sprog: engelsk, spansk, hollandsk, fransk, tysk, italiensk, japansk — **ikke dansk** — [Deepgram Aura-2 languages](https://deepgram.com/learn/aura-2-now-speaks-dutch-french-german-italian-japanese); [Deepgram TTS models docs](https://developers.deepgram.com/docs/tts-models)

**Åbne danske modeller: CoRal / Røst (Alexandra Instituttet)**
- CoRal-projektet: Innovationsfonden bevilgede 14.217.380 kr. (totalbudget 22.172.400 kr.), partnere Alvenir, Corti, Digitaliseringsstyrelsen, Alexandra Instituttet, Københavns Universitet; datasættet indeholder 700+ timer frit tilgængelig dansk tale (fuld samling 1.000 timer, heraf 330 timer samtale), 1.000+ deltagere 11–97 år, dialekter og accenter — [Alexandra: CoRal](https://alexandra.dk/coral/); [Innovationsfonden](https://innovationsfonden.dk/da/press-release/nyt-storstilet-projekt-skal-bringe-dansk)
- Projektet er afsluttet i 2026, men data og modeller er fortsat frit tilgængelige — [Alexandra: CoRal er færdigudviklet](https://alexandra.dk/coral-er-faerdigudviklet-men-samtalen-er-kun-lige-begyndt)
- Røst-v3 TTS: "roest-v3-chatterbox-350m" (finetune af Chatterbox-Turbo) og "roest-v3-chatterbox-500m" (finetune af Chatterbox Multilingual, dansk+engelsk, stemme via audio-prompt); MOS 4,23 bedømt af 20 danske modersmålstalende — [HF: Røst v3 collection](https://huggingface.co/collections/CoRal-project/rost-v3); [HF: roest-v3-chatterbox-500m](https://huggingface.co/CoRal-project/roest-v3-chatterbox-500m); [GitHub alexandrainst/coral](https://github.com/alexandrainst/coral)
- Gratis dansk TTS-træningsdatasæt "coral-tts" udgivet — [Alexandra: nyt gratis datasæt](https://alexandra.dk/nyt-gratis-datasaet-til-at-traene-modeller-med-tekst-til-tale/); [HF dataset coral-tts](https://huggingface.co/datasets/CoRal-project/coral-tts)

**Chatterbox Multilingual / Piper**
- Chatterbox Multilingual (Resemble AI, MIT) understøtter dansk blandt 23 sprog; i blindtest foretrukket over ElevenLabs 63,75 % af tiden (engelsk, leverandørens egen test) — [HF ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox); [Chatterbox multilingual docs](https://chatterboxtts.com/docs/multilingual)
- Piper har danske stemmeprøver (lav-latens, on-device) — [Piper voice samples](https://rhasspy.github.io/piper-samples/)

### Inferences
- Ved ~900 tegn pr. minut tale (ca. 150 ord/min) koster ElevenLabs Flash PAYG ≈ $0.036 pr. minut *agenten taler*; da agenten typisk taler ~40–60 % af samtalen, giver det ≈ $0.015–0.022/samtaleminut — i overensstemmelse med Vapi's pass-through på $0.0146–0.0238. Azure Neural ≈ $0.014 pr. talt minut ⇒ ≈ $0.006–0.009/samtaleminut. Cartesia ≈ $0.042 pr. talt minut.
- Røst-v3 (Chatterbox-baseret) er den eneste åbne danske TTS med publiceret MOS-score; MOS 4,23 er højt, men der er ingen offentlig sammenligning mod ElevenLabs dansk. Selvhosting på GPU vil typisk ligge langt under $0.01/min ved volumen, men kræver drift.
- Ingen kilde giver målte latenstal specifikt for dansk hos nogen kommerciel TTS; ElevenLabs' 75 ms-tal er sproguafhængigt modelmål.

### Gaps
- Google Chirp 3 HD-pris pr. 1M tegn blev ikke hentet.
- Ingen uafhængige kvalitetsvurderinger (MOS/lytte-test) af ElevenLabs, Azure, Google eller Cartesia på **dansk** specifikt blev fundet.
- Røst-v3 latenstid/realtidsfaktor er ikke dokumenteret i modelkortene.

---

## 3. STT med dansk: udbydere, WER og priser

### Takeaway
Deepgram Nova-3 har en dedikeret dansk model til streaming (ca. $0.0077/min, promo $0.0048), og Whisper/gpt-4o-transcribe koster $0.006/min. På CoRals danske testsæt er Whisper-large-v3 markant dårligere (WER 28,3 %) end danske finetunes som Røst-whisper-large-v1 (10,4 %) og hviske-v2 (11,8 %), hvilket understreger at generiske modeller ikke er nok til dansk.

### Cited Findings

**Deepgram**
- Nova-3 har en dansk monolingual model "available for both batch (pre-recorded) and streaming (real-time)"; understøtter Keyterm Prompting (op til 100 domænetermer, fx "MitID"); artiklen giver ingen dansk WER-tal — [Deepgram: Nova-3 German, Dutch, Swedish, Danish](https://deepgram.com/learn/deepgram-expands-nova-3-with-german-dutch-swedish-and-danish-support)
- Sprogoversigt: Nova-3 og Nova-2 understøtter "Danish: da, da-DK" med streaming; Flux (turn-taking-modellen) understøtter **ikke** dansk (kun engelsk + 10 sprog multilingual); svensk og norsk understøttes i Nova-3/Nova-2 — [Deepgram models & languages](https://developers.deepgram.com/docs/models-languages-overview)
- Priser (2026): streaming $0.0077/min normal, PAYG-promo $0.0048/min; batch $0.0043/min; diarization +$0.0020/min (verificeret 8. sept. 2026) — [Cekura Deepgram pricing](https://www.cekura.ai/blogs/deepgram-pricing); [diyai](https://diyai.io/ai-tools/speech-to-text/deepgram-pricing-2026/); [ConvertAudioToText](https://convertaudiototext.com/blog/deepgram-nova-3-explained)

**OpenAI (hentet 29-09-2026)**
- Whisper "$0.006 / minute"; gpt-4o-transcribe "$0.006 / minute" (estimeret); gpt-4o-mini-transcribe "$0.003 / minute" — [OpenAI pricing](https://developers.openai.com/api/docs/pricing)

**ElevenLabs Scribe**
- Scribe v2: "$0.22" pr. time; Scribe v2 Realtime $0.39 pr. time (≈ $0.0065/min) — [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- Scribe v2 understøtter 90+ sprog inkl. dansk ("dan"); 9,11 % gennemsnitlig WER (#14 på Open ASR Leaderboard, primært engelsk) — [ElevenLabs STT](https://elevenlabs.io/speech-to-text); [ElevenLabs Danish STT](https://elevenlabs.io/speech-to-text/danish); [Gladia vs ElevenLabs](https://www.gladia.io/blog/elevenlabs-vs-gladia-speech-to-text-comparison-for-voice-ai-builders)

**Gladia / Speechmatics**
- Gladia Solaria-3: 8,26 % gennemsnitlig WER (#2 på Open ASR Leaderboard) — [Gladia](https://www.gladia.io/blog/elevenlabs-vs-gladia-speech-to-text-comparison-for-voice-ai-builders)
- Speechmatics understøtter 56+ sprog inkl. dansk; Ursa 2 gav 18 % WER-reduktion på tværs af 55 sprog — [Speechmatics AI-info](https://www.speechmatics.com/ai-info)

**Danske WER-data (CoRal read-aloud testsæt, fra Røst-modelkortet)**
- Røst-wav2vec2-315m-v2 (315M): CER 6,5 %, WER 16,3 %; Røst-wav2vec2-315m-v1: CER 6,6 %, WER 17,0 %; Whisper-large-v3 (1540M): CER 11,4 %, **WER 28,3 %**; hviske-v2 (1540M): CER 4,7 %, WER 11,8 %; Røst-whisper-large-v1 (1540M): CER 4,3 %, **WER 10,4 %** — [HF: roest-v2-wav2vec2-315m](https://huggingface.co/CoRal-project/roest-v2-wav2vec2-315m)
- Røst-wav2vec2-v2 evalueret på NST-da, CommonVoice17, Fleurs-da_dk, AlvenirOss, AlvenirWiki med WER 8,0–28,4 % afhængigt af testsæt — [HF: roest-v2-wav2vec2-315m](https://huggingface.co/CoRal-project/roest-v2-wav2vec2-315m)
- Licens "openrail" (OpenRAIL-M): kommerciel brug tilladt, restriktioner på "speech synthesis and biometric identification" — [HF: roest-v2-wav2vec2-315m](https://huggingface.co/CoRal-project/roest-v2-wav2vec2-315m)
- Røst-v1-whisper-1.5b er en finetune af Whisper Large v3 på første CoRal-release — [HF: roest-v1-whisper-1.5b](https://huggingface.co/CoRal-project/roest-v1-whisper-1.5b)
- Åbent dansk ASR-leaderboard (5 testsæt: CoRal conversation, CoRal read-aloud, Common Voice 17, FLEURS, FTSpeech) med reproducerbar evaluering af Whisper, Røst og hviske — [GitHub danish-asr-leaderboard](https://github.com/kasperg3/danish-asr-leaderboard); live-tabel på [HF Space RyeAI/danish-asr-leaderboard](https://huggingface.co/spaces/RyeAI/danish-asr-leaderboard)
- syvai/hviske-v3-conversation er en nyere dansk samtale-ASR-model — [HF: hviske-v3-conversation](https://huggingface.co/syvai/hviske-v3-conversation)
- Alexandra udgav Røst i 2024 som "den bedste åbne danske talegenkendelse" — [Alexandra: afslutningskonference](https://alexandra.dk/afslutningskonference-coral-dansk-taleteknologi-i-verdensklasse/)

### Inferences
- Dansk STT koster i alle tilfælde under $0.01/min (≈ 0,03–0,07 kr/min) og er den billigste komponent i stakken.
- WER-tallene viser, at "understøtter dansk" ikke er lig med god dansk kvalitet: Whisper-large-v3 ligger på 28 % WER på oplæst dansk, mens danske finetunes ligger på 10–12 %. Kommercielle udbydere (Deepgram, Gladia, ElevenLabs) publicerer ingen danske WER-tal, så deres reelle danske kvalitet er udokumenteret.
- Deepgram Flux (den turn-taking-optimerede model) mangler dansk, så danske agenter på Deepgram må bruge Nova-3 + separat endpointing.

### Gaps
- Ingen kommercielle udbydere (Deepgram, Google, Azure, ElevenLabs Scribe, Gladia, Speechmatics) publicerer WER for dansk; leaderboard-tabellen på HF Space kunne ikke hentes (dynamisk indhold).
- Azure/Google STT-priser for dansk streaming er ikke hentet.

---

## 4. LLM'er i voice agents og dansk sprogperformance

### Takeaway
Voice-agenter kører typisk på mellemstore, hurtige modeller (GPT-5-mini/-nano, Claude Haiku/Sonnet, Gemini Flash); token-priserne giver ca. $0.01–0.06 pr. samtaleminut. Der blev ikke fundet uafhængige, publicerede benchmarks for dansk samtalekvalitet i voice-kontekst.

### Cited Findings
- OpenAI (hentet 29-09-2026): gpt-5 $1.25/$10.00; gpt-5-mini $0.25/$2.00; gpt-5-nano $0.05/$0.40; gpt-5.6-sol $4.00/$20.00; gpt-4.1 $2.00/$8.00; gpt-4o-mini $0.15/$0.60 pr. 1M input/output tokens — [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- Anthropic (cache dateret 25-09-2026 i Anthropic's claude-api reference): Claude Opus 5.5 $4.00/$20.00; Claude Sonnet 5.5 $2.00/$10.00; Claude Haiku 4.5 $1.00/$5.00 pr. 1M tokens — [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Retells per-minut LLM-takster (som vist 29-09-2026): Gemini 3.0 Flash $0.016; Claude 4.5 Haiku $0.025; GPT 4.1 $0.045; Gemini 3.5 Flash $0.048; Claude 5 Sonnet $0.064; GPT 5.4 $0.080 — [Retell pricing](https://www.retellai.com/pricing)
- Vapi's OpenAI pass-through: "$0.0077 - $0.0452/min" — [Vapi pricing](https://vapi.ai/pricing)
- Synthflow: LLM $0.02–$0.05/min — [Layer3Labs](https://www.layer3labs.io/guides/synthflow-pricing)
- Famulor's kalkulationsantagelse: GPT-4o $0.01–0.03/min — [Famulor](https://www.famulor.io/blog/ai-voice-agent-pricing-2026-what-10-platforms-actually-cost-per-minute)
- Danske udbydere (Instantcall, RingAI, Rigtigt.dk) oplyser ikke, hvilken LLM de bruger — [Instantcall](https://instantcall.dk/); [RingAI](https://ringai.dk/); [Assistent by Rigtigt.dk](https://assistent.rigtigt.dk/)

### Inferences
- Med en systemprompt på ~2–4k tokens, ~10 LLM-kald pr. 3-minutters opkald og ~100 output-tokens pr. tur, giver gpt-5-mini ca. $0.01–0.02/min og Claude Sonnet 5.5 ca. $0.03–0.06/min (uden prompt-caching). Retells tabel bekræfter denne størrelsesorden.
- Ingen fundne kilder dokumenterer, at én LLM-familie er bedre til dansk talt dialog; valget styres i praksis af latens og pris.

### Gaps
- Ingen offentlige benchmarks for dansk samtalekvalitet (fx tal, adresser, navne, dialektforståelse) på GPT-5/Claude/Gemini i voice-kontekst blev fundet.
- Gemini API-listepriser blev ikke hentet direkte fra Google (kun Retells per-minut-takster).

---

## 5. Telefoni i Danmark: udbydere, nummerkrav, portering og minutpriser

### Takeaway
Danske lokalnumre via Telnyx/Twilio kræver virksomhedsdokumentation (CVR-registreringsbevis, dansk adresse, adressebevis <3 md.) og kan ikke bruges privat; Twilio's danske SIP-trunk-priser er $0.02/min (fastnet) og $0.0524/min (mobil) for terminering. Telefoni udgør typisk 0,05–0,35 kr/min af stakken.

### Cited Findings
- Telnyx Danmark, lokalnumre: "Business Only – Private use is not permitted"; kræver repræsentantens navn, firmanavn, "Local Business registration certificate", "Local Business Registration Number", dansk adresse og "Proof of address (dated within 3 months)"; mobilnumre og toll-free kan have adresse hvor som helst; Requirement Groups obligatoriske for DK siden 16. sept. 2024; EU-borgere kan bruge pas/ID fra ethvert EU-land; numre "start at $1" — [Telnyx Denmark DID Requirements](https://support.telnyx.com/en/articles/5464149-denmark-did-requirements); [Telnyx requirement groups](https://developers.telnyx.com/docs/numbers/phone-numbers/requirement-groups)
- Telnyx Danmark nummerportering: LOA med "a local address is mandatory, the signature must be a wet signature", lokalt skatte-/momsnummer og "Latest Invoice with the current provider"; gælder både lokale og toll-free numre; ingen tidsramme/gebyr angivet — [Telnyx Denmark Number Porting](https://support.telnyx.com/en/articles/3266720-denmark-number-porting)
- Twilio Elastic SIP Trunking Danmark: terminering Danmark $0.0200/min, Danmark mobil $0.0524/min; origination (mobil) $0.0067/min; mobilnummer $15.00/md; optagelse $0.0025/min; lager $0.0005/min/md — [Twilio SIP Trunking Denmark](https://www.twilio.com/en-us/sip-trunking/pricing/dk)
- Twilio's nummerpriser pr. land findes i deres CSV — [Twilio numbers pricing CSV](https://www.twilio.com/content/dam/twilio-com/pricing-data/en/csv/PMded94a0dae30eaaec0f115f22859bd38_SiteNumbersPricing.csv)
- Telefoni-transport via orkestreringsplatforme: Vapi: Twilio inbound $0.008/min, Telnyx $0.0055/min, Vapi SIP gratis — [Vapi pricing](https://vapi.ai/pricing); Retell: $0.015/min (US), nummer $2/md — [Retell pricing](https://www.retellai.com/pricing); Synthflow-managed Twilio $0.02/min — [Layer3Labs](https://www.layer3labs.io/guides/synthflow-pricing)
- Telnyx almindelige opkald $0.002/min ind/ud + SIP-trunking — [Telnyx vs Twilio](https://telnyx.com/resources/telnyx-vs-twilio-which-voice-api-is-better)
- Danske udbydere leverer typisk nummer inkluderet: Rigtigt.dk 1 nummer (op til 3 på Virksomhed-plan) — [Assistent by Rigtigt.dk](https://assistent.rigtigt.dk/); Skaala (NO/SE) inkluderer lokalt nummer — [Skaala pricing](https://www.skaala.ai/en/pricing)

### Inferences
- **Viderestilling (forwarding)**: de danske udbydere (Instantcall, RingAI, Rigtigt.dk) leverer et nyt nummer, som kunden viderestiller sit eksisterende nummer til; det undgår portering og CVR-dokumentation hos Telnyx/Twilio for slutkunden, men lægger kundens egen teleudbyders viderestillingstakst oveni (ikke prissat i denne research).
- Et dansk inbound-opkald via Twilio SIP koster ca. 0,13 kr/min (fastnet) eller 0,34 kr/min (mobil-terminering ved viderestilling til mobil); via Telnyx betydeligt mindre. Telefoni er dermed 5–25 % af all-in-omkostningen.
- Kravet om "Business Only" og CVR-bevis betyder, at danske AI-telefonleverandører reelt skal være reseller/ejer af numrene, ikke kunden.

### Gaps
- Twilio's månedspris for et dansk *lokalnummer* (ikke mobil) og inbound-pris pr. minut for lokalnumre blev ikke hentet (CSV ikke parset).
- Danske teleselskabers viderestillingstakster (TDC/Telenor/Telia/3) er ikke undersøgt.
- Porteringstid og -gebyr i Danmark er ikke dokumenteret hos Telnyx.

---

## 6. All-in omkostning pr. samtaleminut: Vapi+ElevenLabs+OpenAI vs. alternativer

### Takeaway
En typisk Vapi + Deepgram + OpenAI + ElevenLabs + Twilio-stak koster ca. $0.09–0.14/min (0,6–0,9 kr/min) i rene komponentpriser; ElevenAgents ≈ $0.10–0.14; Retell med ElevenLabs ≈ $0.13–0.17; Bland $0.11–0.14 all-in. Danske slutkunde-overtakster på 1,0–2,0 kr/min ligger altså 1,5–3× over rå platformomkostning.

### Cited Findings (komponentpriser, alle citeret i afsnit 1–5)
- Vapi: $0.05 platform + Deepgram $0.0095–0.0099 + OpenAI $0.0077–0.0452 + ElevenLabs $0.0146–0.0238 + Twilio inbound $0.008 — [Vapi pricing](https://vapi.ai/pricing)
- ElevenAgents: $0.08/min + LLM separat + telefoni inkl. — [ElevenAgents pricing](https://elevenlabs.io/pricing/agents)
- Retell: $0.055 + ElevenLabs $0.040 (eller Cartesia $0.015) + LLM $0.016–0.064 + telefoni $0.015 — [Retell pricing](https://www.retellai.com/pricing)
- Bland: $0.11–0.14 all-in — [Bland pricing](https://www.bland.ai/pricing); [PxlPeak](https://pxlpeak.com/blog/ai-tools/bland-ai-pricing)
- Synthflow: $0.09 + LLM $0.02–0.05 + Twilio $0.02 — [Layer3Labs](https://www.layer3labs.io/guides/synthflow-pricing)
- Selvhostet (LiveKit/Pipecat): $0.01 hosting + inferens $0.03–0.07 — [Telnyx om LiveKit](https://telnyx.com/resources/livekit-pricing-scale-voice-ai-costs); [Daily Pipecat Cloud](https://www.daily.co/pricing/pipecat-cloud/)
- OpenAI Realtime (speech-to-speech, erstatter STT+LLM+TTS): ≈ $0.05/min fuld, ≈ $0.016/min mini — [Layer3Labs](https://www.layer3labs.io/guides/openai-realtime-api-pricing)
- Uafhængige "true cost"-estimater: Bland $0.10–0.18; Vapi $0.12–0.25; Retell $0.13–0.24; Synthflow $0.15–0.27 (3. april 2026) — [Famulor](https://www.famulor.io/blog/ai-voice-agent-pricing-2026-what-10-platforms-actually-cost-per-minute)

### Inferences (regnestykke, USD/DKK 6,57)
| Stak | USD/min (lav–høj) | DKK/min (ca.) |
|---|---|---|
| Vapi + Deepgram + OpenAI (mini→stor) + ElevenLabs + Twilio inbound | 0,090–0,137 | 0,59–0,90 |
| Vapi + Deepgram + OpenAI + Azure TTS + Telnyx | ≈0,075–0,110 | 0,49–0,72 |
| ElevenAgents ($0.08) + LLM ($0.01–0.05) | 0,090–0,130 | 0,59–0,85 |
| Retell + ElevenLabs + Gemini Flash / Claude Sonnet | 0,126–0,174 | 0,83–1,14 |
| Retell + Cartesia + Gemini 3.0 Flash | ≈0,101 | ≈0,66 |
| Bland (all-in) | 0,110–0,140 | 0,72–0,92 |
| Synthflow PAYG | 0,130–0,160 | 0,85–1,05 |
| LiveKit/Pipecat selvhostet + egne API-nøgler | ≈0,040–0,080 | 0,26–0,53 |
| OpenAI Realtime mini + LiveKit + Telnyx | ≈0,030–0,040 | 0,20–0,26 |

- Sammenholdt med danske overtakster (Rigtigt.dk 1,0–2,0 kr/min; RingAI 1,6–1,8 kr/min, se afsnit 7) giver en Vapi/ElevenLabs/OpenAI-stak en bruttomargin på ca. 40–65 % pr. overtakstminut — **før** platform-minimum, samtidighedslinjer, telefonnumre, support og udvikling.
- Inkluderede minutter i danske abonnementer (fx 299 kr for 100 min = 2,99 kr/min; 1.499 kr for 1.500 min = 1,0 kr/min) ligger også over rå komponentpris, men de billigste planer (1,0 kr/min inkl.) efterlader kun ~0,1–0,4 kr/min margin, hvis alle minutter bruges.
- Selvhostede stakke (LiveKit/Pipecat + Røst/Chatterbox TTS + åben STT) kan halvere komponentprisen, men kræver GPU-drift og giver EU-only processering, hvilket kan være motivationen for danske udbyderes "EU-server"-claims.

### Gaps
- Ingen dansk udbyder oplyser sin faktiske stak eller enhedsomkostning; marginberegningerne er inferens.
- Regnestykket antager, at agenten taler ~50 % af tiden og ~10 LLM-ture pr. 3 minutter; reelle tal afhænger af use case.

---

## 7. Europæiske og nordiske benchmarkpriser for AI-receptionister

### Takeaway
Danske udbydere ligger på 299–2.999 kr/md med overtakst 1,0–2,0 kr/min; det matcher Norge/Sverige (Skaala 299/1.499 NOK/SEK, overtakst 0,60–2,00 kr/min), Tyskland (fonio 99–299 €/md, 0,15–0,20 €/min) og Holland (49–179 €/md entry, 99–400 €/md typisk). USA-produkter (Dialzara $29, Rosie $49, Goodcall $59, My AI Front Desk $65) er billigere pr. måned, mens UK ligger på £39–£299/md.

### Cited Findings

**Danmark (hentet 29-09-2026)**
- Assistent by Rigtigt.dk (Frederiksberg): Starter 299 kr/md (100 min inkl., overtakst 2 kr/min, 25 SMS); Professionel 799 kr/md (500 min, 1,50 kr/min, 100 SMS); Virksomhed 1.499 kr/md (1.500 min, 1 kr/min, 300 SMS, op til 3 numre); ingen oprettelse, ingen binding — [Assistent by Rigtigt.dk](https://assistent.rigtigt.dk/)
- RingAI (København, CVR 46220811): Starter 999 kr/md + 999 kr oprettelse (300 min ≈ 120–150 opkald, 100 SMS, overtakst 1,8 kr/min, 1 kr/SMS); Growth 1.999 kr/md + 1.999 kr (600 min, 1,7 kr/min); Pro 2.999 kr/md + 2.999 kr (900 min, 1,6 kr/min); AI-salgsassistent pilot fra 2.999 kr — [RingAI](https://ringai.dk/)
- Instantcall: fra 899 kr/md ekskl. moms, "Fast lav pris uden binding"; trænet på "over 30.000 danske samtaler"; "100% GDPR-sikker", data på EU-servere — [Instantcall](https://instantcall.dk/)
- Generelt dansk prisbillede for SMV'er 2026: 400–5.000 kr/md (chatbots/AI-assistenter) — [NextGenAI prisguide](https://nextgen-ai.dk/blog/hvad-koster-en-ai-chatbot-i-2026-prisguide-til-danske-virksomheder)

**Norge**
- Skaala: Essential "299 SEK/NOK" ekskl. moms, 50 min inkl., overtakst "2.00 kr/min"; Business "1,499 SEK/NOK", 400 min inkl., overtakst "0.60 kr/min"; lokalt nummer inkl. — [Skaala pricing](https://www.skaala.ai/en/pricing)
- Snakk.ai: fra $99/md (chatwidget, dedikeret nummer, human handoff), "All data in the EU — never in the US", BankID-integration, 60 dages opsigelse — [Snakk.ai](https://www.snakk.ai/en/ai-resepsjonist)
- Enterprise-opsætning i Norge kan koste 50.000–250.000 NOK; fuldtidsreceptionist 450.000–550.000 NOK/år — [Chatbot Norge prisguide](https://chatbot-norge.no/blogg/chatbot-pris-norge.html); [Voicefleet](https://voicefleet.ai/blog/kostnadsbesparelse-ai-resepsjonist-norske-bedrifter)

**Sverige**
- Telink (7. marts 2026): AI Receptionist tillæg "Från 499 kr/mån" oven på molnväxel "Från 89 kr/användare/mån"; eksempel 20 brugere ≈ 2.279 kr/md; unavngivne per-minut-konkurrenter "Typiskt 3-8 kr per minut"; ekstern telefonpasning 2.000–5.000 kr/md — [Telink](https://telink.se/funktioner/ai-receptionist-pris/)
- Sono (23. aug. 2026): ingen offentlige priser; prissættes "nästan alltid per månad" efter volumen, integrationer og optagelse; menneskelig receptionist ≈ 37.500 SEK/md — [Sono](https://callsono.com/sv/blog/vad-kostar-ai-receptionist/)
- Svaria sammenligner 8 svenske alternativer (Koppla AI, Bokadirekt, AI-Reception.se m.fl.) uden offentlige priser — [Svaria](https://www.svaria.io/jamfor-ai-receptionist); oversigt: [Systemguiden](https://systemguiden.org/jamfor-kategori/ai-receptionist)

**Tyskland (fonio.ai, 20. februar 2026, 10 udbydere)**
- fonio €99–299/md (Solo 1.000 min; Team 3.000 min), derefter €0,15–0,50/min; prepaid €0,20/min uden grundgebyr — [fonio pricing](https://www.fonio.ai/en/pricing/); [fonio sammenligning](https://www.fonio.ai/de/news-cool-stuff/ki-telefonassistent-kosten-10-anbieter-im-vergleich-2025/)
- Placetel €6,90–16,90/md + €0,01/min; smao €69–399/md (100–2.000 min, derefter €0,20–0,30/min); Synthflow €25–1.200/md; goai €39–499/md; VITAS €49–299/md (€0,20–0,28 pr. samtale); voiceOne €32–329/md; Vapi €0,043/min; Bland €256–427/md (€0,094–0,12/min); Parloa custom; setup typisk €200–500 — [fonio sammenligning](https://www.fonio.ai/de/news-cool-stuff/ki-telefonassistent-kosten-10-anbieter-im-vergleich-2025/)
- Andre tyske entry-priser: fra €29/md (Vokaro) og fra €59/md (Voisa) — [Vokaro](https://vokaro.net/kosten/ki-telefonassistent-kosten); [Voisa](https://www.voisa.ai/blog/ki-telefonassistent-kosten)

**Holland**
- 24/7 Antwoord (Emma): €49, €99 eller €179/md ekskl. moms efter antal samtaler — [24/7 Antwoord](https://247antwoord.nl/blog/telefoonservice-uitbesteden-kosten)
- Voicelabs (Robin): fra €149/md — [Voicelabs](https://www.voicelabs.nl/)
- Aanloop AI: telefoni + WhatsApp "€997/mnd all-in"; AI-agenter for MKB €497–4.500/md — [Aanloop AI](https://aanloopai.nl/tarieven/)
- Typisk NL-marked: €99–400/md; entry €99–149; break-even mod menneske ved ~80 samtaler/md — [BizzPower](https://www.bizzpower.com/blog/ai-antwoordservice-vs-telefoonservice)

**UK (priser tjekket juli 2026)**
- IONOS AI Receptionist: £39/md (30 opkald), £69/md (100 opkald), £99/md (ubegrænset); Ringmere fra £49/md (150 min); marked £49–500+/md (simple), £500–2.000+/md (multikanal/hybrid); entry £39–80; midmarked £99–299 — [Motics](https://www.motics.ai/guides/ai-receptionist-cost-uk/); [Hand On Web](https://www.handonweb.com/blog/ai-receptionist-pricing-uk-2026); [Phoenix AI](https://phoenixai.solutions/insights/guides/best-ai-receptionist-uk-2026)

**USA (til reference)**
- Dialzara Starter $29/md (60 min), Growth $99, Pro $199, overtakst $0.48/min; Rosie fra $49/md; Goodcall $59/md; My AI Front Desk $65/md ($99 på egen prisside); Smith.ai fra $292/md (hybrid, $3.50–5.25 pr. opkald); Voctiv $29/md ubegrænset — [GetAira](https://www.getaira.io/blog/ai-receptionist-pricing-guide); [Famulor](https://www.famulor.io/blog/ai-voice-agent-pricing-2026-what-10-platforms-actually-cost-per-minute); [My AI Front Desk pricing](https://www.myaifrontdesk.com/pricing); [GetVoIP](https://getvoip.com/blog/ai-receptionist-pricing/)

### Inferences
- Omregnet til DKK: fonio Solo €99 ≈ 740 kr (1.000 min ⇒ 0,74 kr/min inkl.); fonio overtakst €0,15 ≈ 1,12 kr/min; Skaala Business 1.499 NOK ≈ 945 kr for 400 min (≈2,4 kr/min inkl.), overtakst 0,60 NOK ≈ 0,38 kr/min; IONOS £99 ≈ 840 kr ubegrænset; Dialzara $29 ≈ 190 kr.
- Danske overtakster (1,0–2,0 kr/min) er på niveau med tyske (1,1–1,5 kr/min), over Skaala Business (0,38 kr/min) og under USA-overtakst hos Dialzara ($0.48 ≈ 3,15 kr/min). Danske månedspriser (299–2.999 kr) er 1,5–3× over amerikanske flat-rate-produkter men på niveau med DE/NL/NO.
- RingAI's oprettelsesgebyr (999–2.999 kr) er en atypisk model i Norden; tyske udbydere angiver setup på €200–500 som normalt.
- Navne fra opgavebeskrivelsen "Sindre", "Talkie" og "Vocalime" kunne ikke identificeres som nordiske AI-receptionister i søgningerne — muligvis forkerte/ukendte produktnavne.

### Gaps
- Sindre, Talkie og Vocalime: ingen relevante prisdata fundet.
- Svenske navngivne udbyderes (Svaria, Sono, Koppla AI) konkrete priser er ikke offentlige.
- GBP/SEK/NOK-kurser er antaget, ikke hentet.

---

## 8. GDPR og EU AI Act for AI-telefonagenter i Danmark

### Takeaway
Fra 2. august 2026 skal en AI-telefonagent mundtligt og tydeligt oplyse, at den er en AI, og hvem den ringer på vegne af (AI Act art. 50) — uden overgangsperiode for denne pligt. Optagelse af opkald kræver efter Datatilsynets vejledning (april 2024) enten dokumentationsformål (uden samtykke, hvis nødvendigt) eller mulighed for at sige nej (træning); aktivt samtykke kræves ved AI-analyse af opkald ud over det. EU-datalokation er reelt kun dokumenteret hos ElevenLabs (enterprise) og selvhostede stakke, hvilket danske udbydere bruger som differentiator.

### Cited Findings

**EU AI Act art. 50 (transparens)**
- Fra 2. august 2026 skal en AI-telefonagent i EU oplyse "that it is a machine — and on whose behalf it is calling", mundtligt, i klart sprog, senest ved første interaktion; gentages ved hver ny interaktion (callbacks, opfølgninger), ved overdragelse til menneske; en linje i vilkår, metadata eller vagt "I'm your assistant" er "expressly not enough"; "obvious"-undtagelsen gælder kun hvor "almost no doubt remains" (interne værktøjer), ikke kundevendte agenter på offentlige numre; bevisbyrden ligger hos den, der påberåber sig undtagelsen — [Famulor: Article 50](https://www.famulor.io/blog/eu-ai-act-article-50-what-your-ai-phone-agent-must-say)
- Kommissionens endelige retningslinjer udkom 20. juli 2026 (51 sider); frivillig Code of Practice on Transparency 10. juni 2026; udsættelsen til 2. dec. 2026 dækker kun art. 50(2) (maskinlæsbar mærkning af syntetisk indhold), ikke oplysningspligten i art. 50(1) — [Famulor: Article 50](https://www.famulor.io/blog/eu-ai-act-article-50-what-your-ai-phone-agent-must-say); [Regulation-AI](https://www.regulation-ai.eu/en/transparency-obligations/); [Kommissionens FAQ om art. 50](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act); [Lovtekst art. 50](https://artificialintelligenceact.eu/article/50/)
- Bøder: op til EUR 15 mio. eller 3 % af global omsætning (laveste beløb for SMV'er) — [Famulor: Article 50](https://www.famulor.io/blog/eu-ai-act-article-50-what-your-ai-phone-agent-must-say)
- Holland: NOS rapporterede allerede 2. aug. 2024, at AI-telefonister "direct" skal give sig til kende; Autoriteit Persoonsgegevens bekræftede kravene; Voicelabs kræver, at kunder angiver et nummer til menneskelig overdragelse — [NOS](https://nos.nl/artikel/2625224-geen-twijfel-ai-telefonist-moet-zich-voortaan-direct-prijsgeven)

**Datatilsynet: optagelse af telefonsamtaler (vejledning april 2024)**
- Der er ingen specifikke regler om telefonoptagelse i GDPR/databeskyttelsesloven; den dataansvarlige skal sikre overholdelse af de almindelige regler — [Datatilsynet: Optagelse af telefonsamtaler (PDF, april 2024)](https://www.datatilsynet.dk/Media/638477264404280979/Optagelse%20af%20telefonsamtaler.pdf)
- Dokumentationsformål: lovligt at optage uden samtykke, hvis det er nødvendigt for at dokumentere samtalens indhold, og behovet ikke kan opfyldes uden optagelse; træningsformål: lovligt uden samtykke, hvis den registrerede kan sige nej før eller under samtalen — [Datatilsynet: Optagelse af telefonsamtaler (PDF)](https://www.datatilsynet.dk/Media/638477264404280979/Optagelse%20af%20telefonsamtaler.pdf); [Dansk Erhverv, april 2024](https://www.danskerhverv.dk/presse-og-nyheder/nyheder/2024/april/datatilsynet-andrer-holdning-du-ma-gerne-optage-telefonsamtaler-hvis-du-overholder-disse-krav/); [Jurainfo](https://jurainfo.dk/artikel/nu-bliver-det-nemmere-at-optage-telefonsamtaler)
- Tidligere vejledende tekst (nov. 2020) — [Datatilsynet nyhed 2020](https://www.datatilsynet.dk/presse-og-nyheder/nyhedsarkiv/2020/nov/ny-vejledende-tekst-om-optagelse-af-telefonsamtaler); afgørelse om Erhvervsstyrelsens optagelser (juli 2021) — [Datatilsynet afgørelse](https://www.datatilsynet.dk/afgoerelser/afgoerelser/2021/jul/erhvervsstyrelsens-optagelse-af-telefonsamtaler)
- AI-analyse af optagne opkald (IDA Forsikring-sagen): Datatilsynet fandt, at optagelse og AI-analyse kunne ske inden for reglerne, men samtykkeprocessen var ikke i orden; samtykke skal gives ved aktiv, utvetydig handling — tavshed er ikke nok, men aktivt tastetryk kan udgøre samtykke — [Jurainfo: Datatilsynet og AI-analyse af telefonsamtaler](https://jurainfo.dk/artikel/datatilsynet-har-undersoegt-brugen-af-kunstig-intelligens-til-analyse-af-optagne-telefonsamtaler)
- Datatilsynet har gjort kunstig intelligens til et primært tilsynsfokus i 2026; regulatorisk sandkasse med Digitaliseringsstyrelsen — [Datatilsynet: Kunstig intelligens](https://www.datatilsynet.dk/regler-og-vejledning/kunstig-intelligens); [Datatilsynets årsberetning 2025](https://www.datatilsynet.dk/Media/639105380237831502/Datatilsynets%20%C3%A5rsberetning%202025.pdf)
- Praktisk dansk guide til lovlig AI-optagelse af salgssamtaler (2026) — [Agent360](https://www.agent360.dk/blog/lovlig-optagelse-salgssamtaler-ai-gdpr)

**Datalokation / leverandørernes differentiatorer**
- ElevenLabs: EU-residency kun enterprise; lagring i EU men processering kan ske udenfor; ZRM + API kan begrænse til EU — [ElevenLabs data residency](https://elevenlabs.io/docs/overview/administration/data-residency); certificeringer SOC 2 Type II, ISO 27001, GDPR m.fl. — [ElevenLabs Agents](https://elevenlabs.io/agents)
- Vapi: ingen publiceret EU-residency; Retell: US-lagring + SCC'er; Twilio ConversationRelay: ikke eksplicit besvaret — [30Elevate (26-07-2026)](https://30elevate.com/en/blog/ai-voice-agent-platforms/)
- Danske/nordiske udbydere bruger EU-hosting som salgsargument: Instantcall "100% GDPR-sikker", EU-servere — [Instantcall](https://instantcall.dk/); RingAI "Al data behandles efter dansk og europæisk lovgivning", databehandleraftale, "AI'en oplyser altid tydeligt, at den er en digital assistent" (outbound B2B) — [RingAI](https://ringai.dk/); Snakk.ai "All data in the EU — never in the US" — [Snakk.ai](https://www.snakk.ai/en/ai-resepsjonist)
- Famulor (april 2026): "European companies must pay close attention. Hidden costs arise from penalties if US providers process sensitive data inadequately" — [Famulor pricing](https://www.famulor.io/blog/ai-voice-agent-pricing-2026-what-10-platforms-actually-cost-per-minute)

### Inferences
- En dansk AI-telefonassistent, der bygger på Vapi/Retell med US-processering, kan være GDPR-compliant via SCC'er, men kan ikke ærligt markedsføre "data forlader aldrig EU". Udbydere, der gør det (Instantcall, Snakk), må enten køre ElevenLabs enterprise+ZRM, EU-hostede modeller (Azure EU-regioner, OpenAI EU-endpoints) eller selvhostede open source-modeller (Røst/Chatterbox/hviske).
- Kombinationen af art. 50-oplysningspligt (fra 2. aug. 2026) og Datatilsynets krav om aktiv opt-out/samtykke ved optagelse betyder, at en dansk agent typisk skal åbne opkaldet med ca. to sætninger ("Du taler med en AI-assistent fra X. Samtalen optages til dokumentation; sig til, hvis du ikke ønsker det"). Det koster 5–10 sekunder pr. opkald (≈ 3–5 % af et 3-minutters opkald) — relevant i minutbaseret prissætning.
- RingAI's formulering om AI-oplysning ved outbound tyder på, at ikke alle danske udbydere endnu har eksplicit art. 50-flow for inbound; det kan være et benchmark-parameter.

### Gaps
- Datatilsynets PDF kunne ikke tekstekstraheres i denne session (binært PDF); indholdet er gengivet via søgeresultat-uddrag og sekundære kilder (Dansk Erhverv, Jurainfo). Eksakte citater fra vejledningen bør verificeres direkte.
- Ingen dansk myndighed (Datatilsynet/Digitaliseringsstyrelsen) har fundet at have udgivet specifik vejledning om AI-telefonagenter og art. 50; kun generel AI-vejledning.
- Om ElevenAgents EU-residency dækker selve agent-runtime (ikke kun TTS) er ikke entydigt dokumenteret.
