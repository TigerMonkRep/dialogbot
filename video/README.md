# Forklaringsvideoen (8 sprog)

Videoen på forsiden er bygget her, én version pr. sprog med egen speak, egne skærmtekster og indbrændte undertekster.
Færdige filer ligger i `web/public/video/dialogbot-<sprog>.mp4` (+ `-poster.jpg`, `-thumb.jpg`, `.vtt`).

## Filer
- `script/<sprog>.json` – speak (`voice`: 8 scener × linjer; hver linje er én undertekst) og skærmtekster (`screen`).
  Dansk er kilden; de andre har præcis samme struktur.
- `scene.html` – animationen (1920×1080). `setup(lang, timing)` og `frame(t)` tegner et vilkårligt tidspunkt.
- `prompt.py <sprog>` – teksten til ElevenLabs med `<break>` mellem linjer (0,7 s) og scener (1,6 s).
- `align.py <sprog>` – linjetider fra ElevenLabs' tvungne alignment (`raw/<sprog>-words.json`, ord med start/slut,
  hvor `<break>`-mærkerne skiller linjerne) → `out/<sprog>/timing.json`, `voice.m4a` og `captions.vtt`.
- `render.js <sprog> video|stills t1,t2` – optager scenerne med Playwright og samler dem med ffmpeg.

## Sådan laves en ny version
1. Ret `script/da.json` (og oversættelserne).
2. Lav speak i ElevenLabs med `python3 prompt.py <sprog>` som tekst, model `eleven_multilingual_v2`.
   Stemmer: da Kresten `TyfEd3ZWTCDCX3xmwEqC`, de øvrige = de mandlige stemmer i `app/modules/voices/standard.py`
   (`LANGUAGE_VOICES`). Gem mp3 som `raw/<sprog>-1.mp3`.
3. Transskribér takten i ElevenLabs (scribe) og gem `words` som `raw/<sprog>-words.json`.
4. `mkdir fonts` og kopiér `outfit-latin-wght-normal.woff2` → `fonts/outfit.woff2` og
   `inter-latin-wght-normal.woff2` → `fonts/inter.woff2` fra `web/node_modules/@fontsource-variable/`.
5. `python3 align.py <sprog> && node render.js <sprog> video`, læg lyd på:
   `ffmpeg -i out/<sprog>/silent.mp4 -i out/<sprog>/voice.m4a -map 0:v -map 1:a -c copy -movflags +faststart -shortest …`

## US-udgaven (`us`)
`script/us.json` er den amerikanske udgave af den engelske (amerikanske ord, «Business hours», 9:00 AM). Stemme:
Curtis `l7mlSJVCAXDwFX44amqm` (amerikansk, varm), model `eleven_multilingual_v2`, godkendt af Fürster 13.11.2026.
Speaken er lavet uden ordtider (ElevenLabs-connectoren giver kun lydfilen), så `raw/us-words.json` er bygget fra
pauserne i lyden: `ffmpeg -af silencedetect=noise=-38dB:d=0.3`, pauser ≥ 0,8 s er linjeskift (pausen efter «Just type:»
er ikke et linjeskift) – én «ord»-post pr. linje med start/slut, adskilt af `<break`-poster som i de andre sprog.
