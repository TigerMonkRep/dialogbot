# Optagebrief og importprocedure – udvidelse mod 16 stemmer

Dette er en indkøbs- og optageplan, ikke en dokumentation af eksisterende stemmer. Der findes i dag nul af de
16 stemmer. De to CoRal-TTS-kandidater er professionelle indtalere, hvis dialekt, alder og køn endnu ikke er
vurderet (se `rights.md`).

## Plan (mål, ikke løfte)

| Gruppe | Antal | Aldersspænd (eksempel) | Præcisering |
|---|---|---|---|
| Mand, rigsdansk | 4 | 20–30, 35–45, 50–60, 65+ | Standarddansk uden markant regional farvning |
| Kvinde, rigsdansk | 4 | 20–30, 35–45, 50–60, 65+ | Som ovenfor |
| Mand, jysk | 4 | 20–30, 35–45, 50–60, 65+ | Angiv præcist, fx **let østjysk (Aarhus)** eller **nordjysk (Vendsyssel)**. Ikke "jysk" alene |
| Kvinde, jysk | 4 | 20–30, 35–45, 50–60, 65+ | Som ovenfor |

Regler:
- Alder og dialekt er indtalerens egne oplysninger og vurderes af relevante lyttere; jysk vurderes af
  jyske lyttere.
- Pitchændring af en eksisterende stemme er ikke en ny indtaler og ikke autentisk dialekt.

## Pilot før bestilling

1. Vælg 2 indtalere, fx en let østjysk kvinde og en rigsdansk mand.
2. Optag **30 minutter hver** efter manuskriptet nedenfor.
3. Importér, lav referencekonditionering og kør lyttetest med ≥ 3 danske lyttere, heraf jyske lyttere for
   den jyske stemme.
4. Resultatet afgør, om referencekonditionering er nok, eller om der skal optages mere (1–3 timer) til
   finetuning. Et bestemt antal timer garanterer ikke en perfekt stemme.

## Tekniske krav

- Optagelse: WAV 48 kHz, 24 bit, mono, ingen komprimering.
- Stille rum med støjgulv under –60 dBFS og et fast mikrofonvalg og -afstand gennem hele optagelsen.
- Ingen musik, efterklang, støjfjernelse eller loudness-behandling. Rå optagelser leveres. Vi bevarer
  originalerne og laver selv afledte filer.
- Én sætning pr. fil. Filnavnet er manuskriptets ID (`<indtaler>-<kategori>-<nr>.wav`). Naturlige pauser
  bevares; afbrudte forsøg kasseres af leverandøren.
- Naturlig telefonstemme: venlig og rolig, samme energi gennem hele optagelsen, ingen "speakerstemme".

## Manuskriptkategorier (andel af pilotens 30 min)

| Kategori | Andel | Eksempler |
|---|---|---|
| Hilsner og afslutninger | 10 % | "Hej, du taler med …", "Tak for opkaldet, hav en god dag." |
| Korte spørgsmål | 15 % | "Hvad hedder du?", "Passer torsdag bedre?" |
| Lange forklaringer | 20 % | Ydelser, arbejdsgange, betingelser |
| Tal, beløb, datoer, klokkeslæt | 20 % | "et tusind fire hundrede og femoghalvfems kroner", "onsdag den otteogtyvende oktober klokken halv elleve" |
| Navne og stednavne | 10 % | Aarhus, Rødovre, Sønderborg, Nørresundby, Hjørring |
| Telefonnumre og e-mail | 5 % | "tyve tredive fyrre halvtreds", "info snabel-a …" |
| Nægtelser og forbehold | 10 % | "Tiden er endnu ikke bekræftet." |
| Dialekttypiske sætninger | 10 % | Kun for dialektstemmer. Skrives sammen med indtaleren, så teksten er naturlig for dialekten |

Manuskriptet skal være nye sætninger. **Testsættet `voice_pipeline/eval/testset_da.jsonl` må ikke bruges i
optagelserne**, fordi det er vores målesæt.

## Metadataformat (pr. indtaler, JSON)

```json
{
  "speaker_id": "dk-f-oestjysk-35-45-a",
  "gender": "female",
  "age_range": "35-45",
  "dialect": "let østjysk (Aarhus)",
  "dialect_basis": "Selvoplyst opvækst i Aarhus; vurderet af 3 østjyske lyttere den …",
  "recording": {"date": "…", "studio": "…", "microphone": "…", "sample_rate": 48000, "bit_depth": 24},
  "agreement_rights_record_id": "<uuid fra voice_rights_records>",
  "files": [{"id": "…-hilsen-001", "text": "…", "category": "hilsner"}]
}
```

Ukendte felter sættes til `null`, aldrig gæt.

## Import

1. Leverancen lægges på importmaskinen (ikke i Git).
2. Byg `manifest.jsonl` i samme format som CoRal-importen, kør `python -m voice_pipeline.qc` og gennemgå
   flag manuelt.
3. Del optagelserne i train/validation/test, så tilstødende sætninger og identiske tekster ligger i samme
   split. Test-split må aldrig bruges som reference.
4. `python -m voice_pipeline.select_references` → upload referencer i Operatørvisningen → opret en version
   med rettighedspost af typen `speaker_agreement` → kør kontroller.
5. `voice_pipeline.eval.synthesize_testset` → `listening_test build` → blind lyttetest → registrér resultat
   → telefontest → godkend og aktivér.
