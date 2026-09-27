# Rettighedsoversigt – stemmemodulet

Status pr. 27. september 2026. Intet herunder er juridisk godkendt. Rettighedsposter i systemet
(`voice_rights_records`) står som `unreviewed`, indtil en navngiven operatør har læst kilden og skrevet en note.
Koden sætter aldrig `verified`.

| # | Hvad | Kilde og version | Licens (hvad vi har set) | Status | Resterende afklaring |
|---|---|---|---|---|---|
| 1 | **Kode**: chatterbox-tts | PyPI `chatterbox-tts==0.1.7` ([pypi](https://pypi.org/project/chatterbox-tts/0.1.7/)) | MIT. Licensteksten er læst i pakkens METADATA den 27/9 2026 | Læst, ikke registreret som verificeret | Transitive afhængigheder (torch, transformers 5.2.0, resemble-perth, gradio m.fl.) har egne licenser. Kør licensscanning på `tts_service/requirements.lock` før produktion |
| 2 | **Modelvægte**: Chatterbox Multilingual (`t3_mtl23ls_v2.safetensors`, `s3gen.pt`, `ve.pt`, tokenizer, `conds.pt`) | [huggingface.co/ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox), revision **ikke fastlåst** | **Ikke læst**: huggingface.co er blokeret af udviklingsmiljøets netværkspolitik | **Blokeret** | Læs hele modelkortet og licensen inkl. anvendelsesbegrænsninger ved den valgte revision. Fastlås commit-hashet i `MODEL_REVISION`. En model arver ikke datasættets licens |
| 3 | **Datasæt**: CoRal-TTS | [huggingface.co/datasets/CoRal-project/coral-tts](https://huggingface.co/datasets/CoRal-project/coral-tts), revision fastlåses ved import (`voice_pipeline/sources/coral_tts.lock.json`) | Opgavebeskrivelsen angiver **CC0** og formål talesyntese, med to professionelle indtalere (mand og kvinde, ca. 17 t hver). Offentlige kilder er ikke entydige (se note A) | **Blokeret, indtil kortet er læst** | Læs datasætkortet og licensen ved den fastlåste revision. Bekræft CC0 og at kommerciel talesyntese er tilladt. Notér eventuelle vilkår om indtalernes stemmer |
| 4 | **Datasæt, må ikke bruges**: CoRal (ASR) | [huggingface.co/datasets/CoRal-project/coral](https://huggingface.co/datasets/CoRal-project/coral) | Datasætkortet forbyder talesyntese (ifølge opgavebeskrivelsen) | Udelukket i kode og dokumentation | Andre CoRal-versioner vurderes hver for sig |
| 5 | **Finetuning-reference**: alexandrainst/coral_chatterbox | GitHub (arkiveret) | Ikke læst (GitHub er blokeret for dette miljø) | Ikke brugt | Kun relevant, hvis finetuning vælges. Kontrollér licens og vedligeholdelse |
| 6 | **Nye indtalere** (16-stemmeplanen) | – | Ingen aftaler findes | Ikke startet | Se krav nedenfor. Der er ikke genereret aftaler, underskrifter eller samtykker |

**Note A.** En søgning fandt en side på sprogteknologi.dk om CoRal-projektets TTS-datasæt. Siden beskriver
optagelser på ca. 24 timer pr. indtaler og en "tilpasset OpenRAIL-M-licens med begrænsninger". Det er i
modstrid med opgavebeskrivelsens CC0 og 17 timer. Måske beskriver siden en anden version eller det store
datasæt. Vi har ikke kunnet læse kilden selv. Derfor må stemmerne ikke godkendes, før datasætkortet ved den
fastlåste revision er læst og citeret i rettighedsposten.

## Hvad Dialogbot ejer, og hvad vi ikke ejer

- Dialogbot styrer sin integration: kode, konfiguration, valg af referenceklip, stemmeversioner og
  eventuelle egne checkpoints.
- Åbne optagelser, fx CoRal-TTS, bliver **ikke** eksklusive Dialogbot-stemmer, fordi vi bruger dem. Andre
  kan lave stemmer ud fra de samme optagelser.
- Et finetunet checkpoint er vores afledte værk. Det er stadig underlagt modellens og datasættets vilkår.

## Krav til aftaler med nye indtalere

Hver aftale registreres som en rettighedspost af typen `speaker_agreement`. Dokumentet lægges i den private
bucket (`document_key`), aldrig i Git. Posten skal mindst angive:

- **Aftalegrundlag.** Aftalen (kontrakten) er grundlaget for den kommercielle brug. Samtykke efter GDPR til
  behandling af stemmen som personoplysning registreres særskilt, fordi samtykke kan trækkes tilbage.
- Tilladt brug:
  - syntetisk tale i Dialogbots telefonassistent og kampagner for Dialogbots kunder;
  - eventuelle undtagelser (fx politiske kampagner eller bestemte brancher).
- Kommerciel anvendelse (ja/nej) og territorium.
- Hosting hos underleverandører: Supabase (EU), GPU-udbyder (navngives), Vapi, telefoniudbyder.
- Varighed og opsigelse.
- **Ophør:**
  - stemmen suspenderes (`suspend`);
  - nye samtaler bruger reservestemmen;
  - referenceklip og checkpoints slettes inden for en aftalt frist;
  - allerede afsluttede opkald berøres ikke.
- Vederlag og eventuelle begrænsninger, fx ingen efterligning af indtaleren i andre sammenhænge.
- Indtalerens metadata (alder, dialekt) er selvoplyst og vurderet af lyttere. Den må ikke opfindes.

Der må ikke bruges filmklip, kendisstemmer eller onlineoptagelser uden dokumenteret brugsret.
