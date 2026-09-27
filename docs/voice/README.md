# Dialogbots danske stemmebibliotek – afleveringsrapport

Dato: 27. september 2026. Branch: `claude/cool-wozniak-ho00tr`. Commits og PR fremgår af PR-beskrivelsen.

**Kort status:** Stemmemodulet er bygget ind i den eksisterende platform og kørt i simuleret tilstand:
- register, versioner, rettigheder, kontroller, API, Vapi-integration, separat talemotor, importpipeline,
  evaluering og UI;
- testet ende til ende, fra valg over prøve og gemt valg til ny session og testsamtale.

**Der er endnu ikke genereret rigtig dansk tale.** Udviklingsmiljøets netværkspolitik blokerer
huggingface.co, og både CoRal-TTS og Chatterbox-vægtene ligger dér. Der er desuden ingen GPU i miljøet.
Stemmemodulet er **ikke klar til produktion**. To fungerende stemmer gør heller ikke hele platformen
launchklar.

## Status pr. del

Kolonnerne betyder:
- **Implementeret**: koden er skrevet.
- **Runtime-testet**: koden er kørt i test eller udviklingsmiljø.
- **Menneskeligt vurderet**: vurderet af rigtige lyttere eller en jurist.
- **Deployet**: kører på staging.

| Del | Implementeret | Runtime-testet | Menneskeligt vurderet | Deployet | Blokeret af |
|---|---|---|---|---|---|
| Datamodel og migration (`a8a4f6f5ffaf`), operatørrolle | ✔ | ✔ (op/ned/check) | – | nej (ved merge) | – |
| Stemmeregister: livscyklus, kontroller, rollback, suspension, audit | ✔ | ✔ (pytest, E2E) | – | nej | – |
| Rettighedsposter og gennemgang | ✔ | ✔ | **nej**: ingen post er verificeret | nej | Læsning af model- og datasætkort (huggingface.co) |
| Dansk normalisering, udtaleordbog, testsæt (110 sætninger) | ✔ | ✔ (4.100 tal round-trip) | nej | nej | – |
| Kunde-API: bibliotek, prøve, valg, tildeling, grænser | ✔ | ✔ | – | nej | – |
| Vapi custom-voice: pinning pr. opkald, sætningsstreaming, afbrydelse, reserve | ✔ | ✔ simuleret (pytest, E2E, HTTP-kæde) | – | nej | Rigtig testsamtale kræver TTS-host |
| Separat TTS-tjeneste (Chatterbox, dansk), kø, timeouts, annullering, container og lås | ✔ | ✔ mekanik med fake-motor | – | nej | Vægte (huggingface.co) og GPU-host (budget) |
| CoRal-TTS-import, QC, referencevalg | ✔ | ✔ på syntetisk Parquet | – | – | huggingface.co |
| To CoRal-TTS-kandidatstemmer | kladder via `scripts/voices_register_coral.py` | **nej** | **nej** | nej | Import, syntese, lyttetest, rettigheder |
| Evaluering: testsæt-syntese, blind lyttetest, benchmark, kædetest | ✔ | ✔ (bench og kæde, simuleret) | **afventer** | – | Rigtig lyd |
| UI: `/app/voices` (bibliotek, prøve, velkomst, tildeling, udtale, guidetrin) og `/app/operator/voices` | ✔ | ✔ (Playwright desktop og mobil) | – | nej | – |
| Opsætningsguide: tjek `voice.heard`, prøveopkald genåbnes ved stemmeskift | ✔ | ✔ | – | nej | – |
| Finetuning | ikke udført (ikke nødvendigt før målinger) | – | – | – | Kræver dokumenteret behov og aftalt budget |

## Hvad du kan bruge nu (efter merge)

- Registeret og operatørvisningen: opret rettighedsposter, gennemgå dem og forbered profiler og versioner.
- Kunderne ser en ærlig side: "ingen godkendte stemmer endnu". Telefonen bruger den eksisterende
  ElevenLabs-stemme uændret. Intet ændrer sig for eksisterende opkald, før en stemme er godkendt og aktiv, og
  `TTS_ENGINE=http` er sat.

## Hvad der mangler (i rækkefølge)

1. **Netværksadgang til huggingface.co** for udviklingsmiljøet, eller kør importen og de første
   syntesetests på en maskine med adgang:
   - `voice_pipeline.import_coral_tts --sample 20`;
   - læs datasætkortet og Chatterbox-modelkortet og registrér gennemgangen (`rights.md`).
2. **Budget til én GPU-host** (forslag: Hetzner GEX44, €184/md. + €79 i opsætning; se `costs.md`). Sæt den
   op efter `operations.md` §4.
3. Syntetisér testsættet for begge kandidater og mål latens (`bench`).
4. **Blind lyttetest** med ≥ 3 danske lyttere, og registrér resultatet.
5. **Rigtig testsamtale** via Vapi og registrering som `telephony_test`.
6. Godkend og aktivér som pilot eller platformstemme. Først derefter kan kunder vælge dem.
7. Udvidelse mod 16 stemmer: indkøb af indtalere med aftaler efter `recording-brief.md`, med en pilot først.

## Dokumenter

- `ADR-003-voice-library.md`: arkitekturbeslutning
- `api.md`: API-kontrakt (kunde, operatør, Vapi custom-voice, intern TTS)
- `rights.md`: rettighedsoversigt, faktisk gennemgang og resterende afklaringer
- `operations.md`: migration, rollback, Supabase-bucket, Vercel, TTS-host, miljøvariabler, alarmer
- `costs.md`: prissat pilot og skaleringsmulighed med datoer, links og antagelser
- `recording-brief.md`: optagebrief, manuskriptkategorier, metadata og importprocedure
- `testing.md`: kommandoer, målte værdier og simuleret/ikke kørt
- `evidence/`: JSON-resultater fra kædetest og benchmark (simuleret, mærket)
