# Omkostninger – stemmemodulet (estimat)

Priser er fundet den 27. september 2026 via de angivne kilder. De skal bekræftes på udbyderens egen prisside før
køb. Ingen ressourcer er bestilt. Gratis modelvægte betyder ikke gratis drift.

## Priskilder

| Post | Pris | Kilde |
|---|---|---|
| Hetzner GEX44 (RTX 4000 SFF Ada, 20 GB VRAM, DE/FI) | €184/md. + €79 i opsætning, fast pris | [Hetzner pressemeddelelse](https://www.hetzner.com/pressroom/new-gpu-server/), [bex.co jul. 2026](https://bex.co/blog/2026/07/13/hetzner-gex44-gpu-pricing-break-even) |
| RunPod Secure Cloud L4 (24 GB) | $0,49/time (sep. 2026) | [Flexprice](https://flexprice.io/blog/runprod-pricing-guide-with-gpu-costs), [RunPod](https://www.runpod.io/pricing) |
| Modal L4 / A10G (serverless, per sekund) | ≈ $0,80/time / $1,10/time kun mens containeren kører | [ComputePrices](https://computeprices.com/providers/modal), [Modal](https://modal.com/blog/nvidia-a10g-price-article) |
| Vapi platform | $0,05/min + udbydernes kostpris | [CloudTalk](https://www.cloudtalk.io/blog/vapi-ai-pricing/), [Cekura](https://www.cekura.ai/blogs/vapi-ai-pricing) |
| Deepgram Nova-3 streaming | $0,0058/min (multilingual); $0,0048/min kampagnepris / $0,0077/min normalpris (monolingual) | [HappyRobot](https://www.happyrobot.ai/hub/deepgram-pricing), [Deepgram](https://deepgram.com/learn/introducing-nova-3-speech-to-text-api) |
| Supabase Storage | $0,021/GB/md. over det inkluderede, egress $0,09/GB | [Supabase](https://supabase.com/docs/guides/storage/pricing) |
| ElevenLabs via Vapi (det, egen TTS erstatter) | ca. $0,04/min i typiske opstillinger | [CloudTalk](https://www.cloudtalk.io/blog/vapi-ai-pricing/) |

## Antagelser (skal erstattes af målinger)

- Assistenten taler ca. 40 % af samtaletiden. 1 samtaleminut giver ca. 0,4 genererede lydminutter.
- Syntesehastighed (realtidsfaktor, RTF) er ikke målt. En offentlig måling af en streaming-variant viser
  RTF ≈ 0,5 på RTX 4090 ([chatterbox-streaming](https://github.com/davidbrowne17/chatterbox-streaming)).
  Vi antager konservativt RTF ≈ 1 på L4 eller RTX 4000 Ada. Det svarer til 1–2 samtidige samtaler pr. GPU
  inden for 1,5 s p95. **Mål det med `voice_pipeline.eval.bench` før køb af mere end én GPU.**
- Én model pr. GPU (modellens stemmetilstand er delt). Flere samtidige samtaler kræver flere replikaer.

## A. Lille pilot (anbefalet start)

| Post | Valg | Pris pr. måned | Bemærkning |
|---|---|---|---|
| GPU-tomgang og -drift | 1 × Hetzner GEX44, varm hele tiden | €184 (+ €79 én gang) | Fast pris uanset minutter. EU-hosting |
| Genererede lydminutter | indeholdt | 0 ekstra | Op til GPU'ens kapacitet (1–2 samtidige samtaler, antaget) |
| Samtaleminutter (Vapi) | uændret | $0,05 × minutter | Findes allerede |
| Talegenkendelse (Deepgram) | uændret | ≈ $0,006 × minutter | Findes allerede |
| Dialogmodel (LLM) | uændret | afhænger af model og længde | Findes allerede |
| Telefoni (nummer og minutter) | uændret | ikke prissat | Dansk nummer er endnu ikke købt. Prisen vises før køb |
| Lager (Supabase) | referenceklip ≈ 10–50 MB | ≈ $0 | Et fuldt CoRal-TTS-udtræk (≈ 10–15 GB WAV) ligger på importmaskinen, ikke i Supabase |
| Træning | ingen | 0 | Kun referencekonditionering |

**Eksempel ved 1.000 samtaleminutter pr. måned.** Egen TTS koster €184 fast. ElevenLabs ville koste
≈ $40 (1.000 × $0,04). Ved lav volumen er egen stemme altså **dyrere**. Den er begrundet i kontrol, egne
danske stemmer og dialekter, ikke i pris. Break-even er ved ca. 5.000 samtaleminutter pr. måned, hvis
antagelserne holder.

**Alternativ med kun åbningstid:** Modal L4 med et varmt vindue på hverdage 8–18 (≈ 220 t) koster
≈ $176/md. Uden for vinduet er der koldstart på minutter, så nye opkald bruger reservestemmen.

## B. Skaleringsmulighed

- N GPU-replikaer bag en load balancer. Hver replika håndterer 1–2 samtidige samtaler (antaget).
- **20 samtidige samtaler:** ≈ 10–20 × GEX44 (€1.840–3.680/md.) eller RunPod L4 døgnet rundt
  (≈ $358/md. pr. replika).
- Mål først, og vælg derefter hardware efter målt p95. En enkelt større GPU (L40S eller H100) kan være
  billigere pr. samtale, hvis modellen batcher. Chatterbox kører i dag én ad gangen pr. instans.

## C. Finetuning (ikke planlagt)

Det kræver aftalt budget og kun, hvis lyttetesten viser et konkret behov. Et forsøg med 1 × A100 80 GB i
10–30 timer koster størrelsesordenen $20–60 i GPU-tid (RunPod og Modal har timepriser i
[priskilderne](https://computeprices.com/providers/runpod)). Dertil kommer datarens, evaluering og lyttetest.
