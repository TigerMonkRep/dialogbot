# Rettighedsoversigt – stemmemodulet

Status pr. 27. september 2026. Intet herunder er juridisk godkendt. Rettighedsposter i systemet
(`voice_rights_records`) står som `unreviewed`, indtil en navngiven operatør har læst kilden og skrevet en note.
Koden sætter aldrig `verified`.

| # | Hvad | Kilde og version | Licens (hvad vi har set) | Status | Resterende afklaring |
|---|---|---|---|---|---|
| 1 | **Kode**: chatterbox-tts | GitHub [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) ved commit `5de7a54aa4e5e2baadb0182dde554908b48b85c2` (21/7 2026). Pakkeversionen hedder stadig 0.1.7, men PyPI-udgaven 0.1.7 kan kun indlæse V2 | MIT. `LICENSE` er læst ved commit'en den 27/9 2026 ("MIT License, Copyright (c) 2025 Resemble AI") | Læst, ikke registreret som verificeret | Transitive afhængigheder (torch, transformers 5.2.0, resemble-perth, gradio m.fl.) har egne licenser. Kør licensscanning på `tts_service/requirements.lock` før produktion |
| 2 | **Modelvægte**: Chatterbox Multilingual **V3** (`t3_mtl23ls_v3.safetensors`, `s3gen.pt`, `ve.pt`, `grapheme_mtl_merged_expanded_v1.json`, `conds.pt`, `Cangjie5_TC.json`) | [huggingface.co/ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox) ved revision `5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18` (10/6 2026) | MIT. Modelkortet er læst den 27/9 2026: `license: mit`, dansk (`da`) er understøttet, V3 anbefales som den generelle flersprogede model, og al lyd får et Perth-vandmærke. Kortet har ingen yderligere anvendelsesbegrænsninger ud over en ansvarsfraskrivelse ("Don't use this model to do bad things") | Læst, ikke registreret som verificeret | En navngiven person skal gennemgå og registrere posten. Modellen arver ikke datasættets licens |
| 3 | **Datasæt**: CoRal-TTS | [huggingface.co/datasets/CoRal-project/coral-tts](https://huggingface.co/datasets/CoRal-project/coral-tts) ved revision `3dd07186e806fdc3931a3d17b4a16373b2a81e8a` (14/10 2024), fastlåst i `voice_pipeline/sources/coral_tts.lock.json` | **CC0-1.0.** Datasætkortet er læst den 27/9 2026: formål `text-to-speech`, to professionelle danske indtalere (kvinde og mand, ca. 17 timer hver) optaget af Nota, tekster udvalgt af Alexandra Instituttet. `speaker_id` er `mic` og `nic`; kortet siger ikke, hvem der er kvinden | Læst, ikke registreret som verificeret | CC0 frasiger ophavsret, men indtalernes personlige stemme er ikke nødvendigvis omfattet. Afklar hos Alexandra Instituttet eller Nota, om kommerciel telefonbrug med genkendelige stemmekloner er i orden, før platformsgodkendelse |
| 4 | **Datasæt, må ikke bruges**: CoRal (ASR) | [huggingface.co/datasets/CoRal-project/coral](https://huggingface.co/datasets/CoRal-project/coral) | OpenRAIL-D (tilpasset OpenRAIL-M). Kortet er læst den 27/9 2026: "Speech Synthesis and Biometric Identification are not allowed using the CoRal dataset." | Udelukket i kode og dokumentation | Andre CoRal-versioner vurderes hver for sig |
| 5 | **Finetuning-reference**: alexandrainst/coral_chatterbox | GitHub (arkiveret) | Ikke læst | Ikke brugt | Kun relevant, hvis finetuning vælges. Kontrollér licens og vedligeholdelse |
| 6 | **Nye indtalere** (16-stemmeplanen) | – | Ingen aftaler findes | Ikke startet | Se krav nedenfor. Der er ikke genereret aftaler, underskrifter eller samtykker |

**Note A (løst 27/9 2026).** Siden på sprogteknologi.dk om en "tilpasset OpenRAIL-M-licens med begrænsninger"
beskriver ASR-datasættet `CoRal-project/coral` (række 4), ikke CoRal-TTS. Begge kort er nu læst ved de
revisioner, der står ovenfor: CoRal-TTS er CC0-1.0 med talesyntese som formål, mens CoRal-ASR forbyder
talesyntese.

**Note B (V3-kode).** Resemble AI har også lagt en V3-kode på Hugging Face, i demo-siden
`ResembleAI/Chatterbox-Multilingual-TTS-V3` ved revision `b21d9d0`. Den kode er en ældre, tilpasset kopi, der
afviger fra GitHub. Vi bruger GitHub-koden. Begge indlæser de samme vægtfiler (`t3_mtl23ls_v3.safetensors`,
`s3gen.pt` og `ve.pt`).

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
