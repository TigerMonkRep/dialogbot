# Egen stemme – kunder indtaler selv

Kunden kan indtale sin egen stemme direkte i Dialogbot (`/app/voices/own`, kun administratorer og ejere). Stemmen
bruges kun i kundens eget arbejdsrum.

## Forløb

1. **Samtykke.** Indtaleren skriver sit fulde navn under en fast tekst (version 1, se `CONSENT_TEXT` i
   `app/modules/voices/own_voice.py`) og bekræfter. Navnet skal matche indtalerens navn. Teksten gemmes ordret med
   tidspunkt, bruger og arbejdsrum og registreres som en rettighedspost af typen `speaker_agreement` med status
   `unreviewed`. Koden godkender aldrig samtykket selv.
2. **Manuskript.** Kort manus (15 sætninger, ca. 2 minutter) eller standardmanus (400 sætninger, ca. 25–30
   minutter). Firmanavn, ydelse og by bliver flettet ind, så indtaleren læser om sin egen forretning. Under hver
   sætning står et forslag til, hvordan tal og datoer udtales.
3. **Optagelse i browseren.** 16-bit WAV uden komprimering og uden browserens støjfjernelse. Hver sætning bliver
   tjekket ved upload: gyldigt format, længde (0,8–25 s), lydniveau, overstyring og baggrundsstøj. Beskederne i
   appen fortæller, hvad der skal gøres anderledes.
4. **Indsendelse.** Kan først ske, når alle sætninger er godkendt. Der bliver oprettet en privat stemme
   (`origin=customer_recorded`, `visibility=workspace`) med en reference på 7–12 sekunder fra sammenhængende, rene
   optagelser. Versionen står som `pending_review`, og de automatiske kontroller er kørt.
5. **Gennemgang.** En operatør læser samtykket og sætter rettighedsposten til `verified`, kører kontrollerne igen,
   lytter til en prøve og godkender og aktiverer stemmen som pilot i arbejdsrummet. Først derefter kan kunden vælge
   stemmen.
6. **Tilbagetrækning.** "Træk samtykket tilbage" sletter optagelserne og referencen i lageret med det samme, sætter
   alle versioner til `retired` og rettighedsposten til `blocked`. Nye opkald bruger reservestemmen med det samme.

## Kvalitet og forbehold

- Stemmen laves med referencekonditionering i Røst-v3. Ligheden med en ny indtaler kan variere. I en test med en
  mandlig indtaler blev stemmelejet løftet fra 98 til 105–118 Hz, og ligheden var 0,82 (speaker-encoder cosine;
  0,97 mellem to stykker af samme optagelse). Det står i appen.
- Standardmanuskriptet er lavet til en senere finjustering pr. stemme. Den kræver GPU-tid og et aftalt budget.
- Samtykketeksten er ikke gennemgået af en jurist. Det skal ske før kommerciel drift, også i forhold til Røst-licensens
  punkt 4(b) (efterligning af en persons stemme kræver forudgående, informeret samtykke).

## API

| Metode | Sti | Hvad |
|---|---|---|
| GET | `/workspaces/{ws}/own-voices/manuscripts/{kort\|standard}?firma=&ydelse=&by=` | Personligt manuskript + samtykketekst |
| GET | `/workspaces/{ws}/own-voices` | Indtalinger med fremdrift og status |
| POST | `/workspaces/{ws}/own-voices` | Start med samtykke (`speaker_name`, `consent_typed_name`, `consent_accepted`, `manuscript`, `speaker_gender`, `firma`, `ydelse`, `by`) |
| PUT | `/workspaces/{ws}/own-voices/{id}/recordings/{sentence_id}` | Rå WAV (højst 6 MB) → kvalitetstjek |
| GET | `/workspaces/{ws}/own-voices/{id}/recordings/{sentence_id}/audio` | Afspil egen optagelse |
| POST | `/workspaces/{ws}/own-voices/{id}/submit` | Opret privat stemme til gennemgang |
| DELETE | `/workspaces/{ws}/own-voices/{id}` | Træk samtykket tilbage og slet |

Manuskripterne ligger i `voice_pipeline/manuscripts/` og bygges med `python -m voice_pipeline.manuscripts.build`.
Buildet stopper, hvis en sætning også findes i evalueringstestsættet.
