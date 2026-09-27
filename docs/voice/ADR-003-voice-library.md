# ADR-003 — Dansk stemmebibliotek og egen talesyntese

Dato: 27. september 2026. Status: vedtaget for første leverance (to kandidatstemmer), ikke godkendt til produktion.

## Kontekst

Virksomheder skal kunne vælge en dansk stemme, høre en prøve og bruge den i telefonassistenten og
udgående kampagner. Webchat bruger ikke tale. Platformen findes i forvejen: FastAPI + SQLAlchemy + Alembic
+ PostgreSQL (Supabase, schema `dialogbot`), outbox/worker og Next.js-BFF (Vercel). Den har også arbejdsrum
med roller, kapabilitetsregister, serverberegnet opsætningsplan og Vapi-telefoni med ElevenLabs-stemme.
Det er bekræftet i koden (`app/`, `web/`, `infra/render.yaml`).

## Beslutninger

1. **Udvid den eksisterende platform.** Vi bygger ikke et parallelt system. Stemmemodulet består af:
   - `app/modules/voices/` med fire nye tabeller;
   - kolonner på `phone_numbers`/`campaigns`;
   - operatørrollen `users.is_platform_operator`, sat med `scripts/grant_operator.py`.

   Det genbruger auth, roller, arbejdsrumsadskillelse (`get_scoped`), auditlog, opsætningstjek og guide.
2. **Talesyntese er en separat tjeneste** (`tts_service/`, egen container med GPU og CUDA 12.4). API'et
   indlæser aldrig en model. API'et og Vercel-funktionerne kalder den over HTTPS med en hemmelig token.
3. **Første motor: Chatterbox Multilingual** (Resemble AI, kode under MIT) med `language_id="da"`.
   - Stemmen bestemmes af referenceklip (konditionering). Det er ikke finetuning og ikke en ny model.
   - Vægte hentes fra Hugging Face ved et fastlåst commit. Tjenesten nægter at starte uden et
     40-tegns commit-hash og afviser stemmeversioner, der er godkendt til en anden revision.
   - English-only Turbo er fravalgt.
   - Modellens Perth-vandmærke bevares.
4. **Uforanderlige stemmeversioner** med modelrevision, referenceklip (nøgle og sha256), indstillinger,
   rettighedsposter og kontrolresultater.
   - Livscyklus: kladde → afventer kontrol → godkendt → aktiv ↔ suspenderet → udfaset.
   - Ved aktivering beholdes forrige version som godkendt, så rollback er ét kald.
5. **Publicering kræver kontroller, der ikke kan forfalskes i koden:**
   - `rights`: alle rettighedsposter er verificeret af en navngiven operatør med note.
   - `normalization`: testsættets kritiske værdier.
   - `synthesis_smoke`: rigtig motor; den simulerede tæller kun i dev/test.
   - `listening_test`: mindst 3 lyttere, gennemsnit ≥ 4, ingen kritiske fejl.
   - `telephony_test`: opkalds-ID.

   Platformstemmer kræver alle fem. En privat pilot for ét arbejdsrum kræver de tre første og vises som
   "Pilot".
6. **Pinning pr. samtale.** Når Vapi beder om en assistent, oprettes en `voice_session` med version,
   indstillinger og udtaleordbog. Vapi får `custom-voice` med sessionens URL, så en opdatering eller
   rollback aldrig skifter stemme midt i et opkald. Suspendering stopper stemmen straks (503), og Vapi
   bruger den godkendte reservestemme (`fallbackPlan`).
7. **Dansk normalisering før syntese** (`danish.py`). Værdier ændres aldrig; tests bekræfter det ved at
   parse tallene tilbage.
   - Tal, beløb, datoer, klokkeslæt, telefonnumre i par og e-mail staves ud.
   - Udtaleordbogen er versioneret.
   - Opdeling i taleenheder sker kun mellem sætninger.
8. **Ikke-streamende model → sætningsvis streaming.** Første taleenhed syntetiseres, før svaret starter;
   fejler den, bliver det til 503 og derefter reservestemme. De øvrige enheder sendes, efterhånden som de
   er klar. Afbryder kunden, stopper vi ved næste enhed og annullerer i tjenesten. Tiden til første lyd
   rapporteres pr. kald (`x-first-audio-ms`, `voice_sessions.stats`).
9. **Privat lager** (lokal mappe i dev, privat Supabase-bucket i drift) til referenceklip, aftaler og
   prøvecache. Adgang sker kun server-side med service-role-nøglen.
   - Nøgler valideres.
   - Cache-nøgler indeholder version, modelrevision, indstillinger, tekst og format.
   - Kun standardprøver caches; egne tekster og samtaletekster caches eller logges aldrig.
   - RLS beskytter ikke backendens privilegerede forbindelse; adskillelsen ligger i API'et og er testet.

## Konsekvenser

- Vi skal drive en GPU-ressource, også når der ikke ringes (se `costs.md`).
- En stemme er kun så god som referencen og modellens danske. Første kvalitetsmål er ≥ 4/5 på
  forståelighed og naturlighed ved blind lyttetest. Det er ikke målt endnu.
- Finetuning, fx med `alexandrainst/coral_chatterbox` (arkiveret), tages først op, hvis målinger viser et
  konkret behov og der er aftalt budget.
- Uden en aktiv Dialogbot-stemme bruges den eksisterende ElevenLabs-stemme uændret, så intet går i stykker.
