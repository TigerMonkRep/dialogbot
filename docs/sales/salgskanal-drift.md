# Dialogbots interne salgskanal – drift

Status: **fase 1 og 2 implementeret** (søgning, sikker research, profil, manuskript, simulation, kontaktgrundlag,
kontaktpolitik, spærreliste, interne kampagner, testopkald, opkald og transskript). Fase 3–4 (tilbud/ordre, møder,
Peters værktøjer under opkald, statistik, lyd, retention) er **ikke implementeret**. Analyse og plan:
`docs/sales/intern-salgskanal.md`. Kun platformsoperatører har adgang (`/app/operator/salg`, API `/api/v1/operator/salg/*`).

## Tilstande (`SALES_OUTBOUND_MODE`)

| Værdi | Hvad virker |
|---|---|
| `off` (standard) | Kun statussiden `GET /operator/salg`. Alle andre ruter svarer 501 `sales_channel_off`; workeren kører ingen søgejob. |
| `research` | Søgning, import, research af hjemmesider, profil, manuskript, integrationsregister. |
| `simulation` | Som `research` + simulerede samtaler. Anbefalet til staging og til at prøve kanalen af. |
| `test` | Som `simulation` + rigtige opkald, men kontaktpolitikken giver kun ALLOW til numre i `SALES_TEST_NUMBERS`. |
| `live` | Rigtige opkald til kontakter, som politikken tillader. Kræver Vapi og `TELEPHONY_PROVIDER=live` (ellers starter processen ikke). |

Øvrige variabler: `docs/environment-variables.md` (afsnittet om salgskanalen).

## Sådan køres en søgning

1. Operatør → **Dialogbots salg** → **Find virksomheder**. Vælg branche(r) (Google-typer står under hver), evt. egne
   Google-typer eller søgeord, og et område: by/bydel (slås op i postnummerlisten; ellers ét Google-opslag), postnumre
   (ét delområde pr. postnummer, 3 km), eller radius (≤ 50 km; over 5 km deles i overlappende cirkler, højst 60).
2. **Beregn forbrug** viser overslaget (højst antal søgeforespørgsler, detaljeopslag og kroner). **Start søgning** lægger
   jobbet i kø; workeren tager det inden for et minut og arbejder højst 40 sekunder pr. gennemløb.
3. Fremskridt: fundet, undersøgt, sprunget over (med grund: kendt i forvejen, ikke relevant, eksisterende kunde),
   ufuldstændige (fx lukket ifølge Google), mulige dubletter, forespørgsler og anslået pris. **Stop** virker mellem
   forespørgsler; **Genoptag** fortsætter fra næste trin (et sat-på-pause job efter dagsloftet eller en midlertidig
   Google-fejl).
4. Uden `GOOGLE_PLACES_API_KEY` bruges demo-data (`app/modules/sales/data/demo_places.json`): fiktive virksomheder,
   `.invalid`-domæner og numre i det ubrugte danske 1x-område. UI'et viser "Demo-data".
5. Fallback uden Google: **Importér egen liste (CSV)** med kolonnerne navn, cvr, hjemmeside, telefon, e-mail, postnr.

## Google Places (New)

Verificeret mod Googles dokumentation 30. oktober 2026 (Text Search, Place Details, Place Data Fields, Policies):

- Text Search: `POST https://places.googleapis.com/v1/places:searchText`, headers `X-Goog-Api-Key` og
  `X-Goog-FieldMask`. Body: `textQuery` ("frisør i 8000 Aarhus C"), `includedType` + `strictTypeFiltering: true`,
  `locationBias.circle {center {latitude, longitude}, radius ≤ 50000}`, `languageCode: "da"`, `regionCode: "DK"`,
  `pageSize: 20`, `pageToken`. Højst 60 resultater pr. forespørgsel (3 sider) – derfor delområder.
- Feltmaske for søgningen (Text Search **Pro**):
  `places.id,places.displayName,places.formattedAddress,places.addressComponents,places.location,places.types,places.primaryType,places.businessStatus,places.googleMapsUri,nextPageToken`
- Place Details, kun for nye, relevante virksomheder i drift: `GET https://places.googleapis.com/v1/places/{id}?languageCode=da&regionCode=DK`
  med feltmasken (uden `places.`-præfiks, **Enterprise**):
  `websiteUri,nationalPhoneNumber,internationalPhoneNumber,regularOpeningHours,rating,userRatingCount`
- Fritekst-sted, der ikke er en dansk by/bydel i postnummerlisten: én Text Search med `places.id,places.location` (Pro).
- Google fakturerer efter det højeste SKU, feltmasken rammer. Overslaget bruger analysedokumentets listepriser (Pro $32,
  Enterprise $35 pr. 1.000 ≈ 0,22/0,24 kr. pr. forespørgsel) – **ikke genverificeret** mod Googles prisliste, som
  dokumentationssiderne henviser til; den gratis månedskvote er ikke fratrukket.
- Forbrug: hver forespørgsel tælles i `sales_search_jobs.budget.by_day`; `SALES_SEARCH_DAILY_REQUEST_CAP` (standard
  500) er et hårdt loft pr. dansk døgn. Sæt også kvoteloft og budgetalarm i Google Cloud-projektet `dialogbot-513209`.
- Brugsret: `place id` gemmes permanent. Øvrige Google-felter har `google_fetched_at`; et dagligt job (efter kl. 03)
  genopfrisker felter ældre end `GOOGLE_PLACES_CACHE_DAYS` (30) via Place Details eller nulstiller dem og sletter
  Google-fakta. Googles politikside siger, at indhold ikke må caches ud over de tilladte undtagelser og henviser til
  Service Specific Terms for den præcise regel; 30 dage er analysedokumentets tal. Google-data vises med kilden
  "Google"; ingen anmeldelsestekster; ingen scraping af Google-sider.
- Google-typerne pr. branche (`sales/script.py` `INDUSTRIES[...]["google_types"]`) skal være gyldige "Table A"-typer;
  tjek nye typer mod Googles liste, før de tilføjes under Brancher.
- Postnummerlisten (`app/modules/sales/data/postnumre.csv`) er fra GeoNames (CC BY 4.0) med omtrentlige midtpunkter;
  DAWA, som analysedokumentet nævner, er lukket (svarer 410).

## Dubletter og eksisterende kunder

- Samme Google place id: opdateres, tilføjes ikke igen ("kendt i forvejen").
- Samme CVR, samme domæne + postnummer eller samme telefon: gemmes og markeres **mulig dublet** – flettes aldrig.
- Samme domæne, anden adresse: **mulig afdeling**. Samme navn i et andet postnummer: to virksomheder.
- Eksisterende kunde = et arbejdsrum med en aftale, hvis virksomhedsprofil har samme domæne eller CVR. Markeres og
  springes over, når "Spring eksisterende kunder over" er valgt.

## Research af en hjemmeside

Kun gennem `app/core/safe_fetch.py`: http(s) på 80/443, ingen brugernavn/adgangskode i URL'en, DNS slås op og **alle**
adresser tjekkes (privat, loopback, link-local, metadata, IPv4-mapped m.fl.); forbindelsen går til den tjekkede IP
(`Host`/SNI = navnet), så DNS-rebinding ikke virker; redirects (højst 4) tjekkes pr. hop; robots.txt for
`DialogbotResearch` respekteres (cache 24 t); 8 sider, 2 samtidige pr. domæne, 2 s pause, 10 s og 1,5 MB pr. side.
Videnimporten og sociale links bruger samme modul (videnimporten uden robots, fordi ejeren selv beder om sin side).

Linjer, der ligner instruktioner til en AI, fjernes før udtrækket. Modellen (prompt `sales-research-v1`, uden værktøjer)
svarer i et fast skema; en værdi gemmes kun, hvis den står på siderne (telefon/CVR ciffer for ciffer). Højeste sikkerhed
kræver et ordret citat. Findes et gyldigt CVR, slås reklamebeskyttelse op, når `CVR_USERNAME/PASSWORD` er sat – ellers
"ukendt". AI-forbruget logges på salgsarbejdsrummet (`SALES_WORKSPACE_ID` kræves).

## Profil, manuskript og simulation

- Profil: ≤ 3 fakta med kilde, ≤ 2 hypoteser (altid spørgsmål), relevant ydelse.
- Manuskript `peter-sales-v1`: teksten i `app/modules/sales/data/peter-sales-v1.txt` (afsnit E §9) med felterne udfyldt;
  et felt uden værdi fjerner hele sætningen. Validering: ingen pladsholdere, kun beløbene i prislisten (2.495, 4, 2, 1,50 og 5.000 kr.) fra
  `billing/prices.py`, integrationsstatus fra registret, fakta med gyldig kilde, funktioner fra godkendt viden,
  kalenderbooking kun når integrationen er AKTIV, reklamebeskyttede virksomheder afvises. Godkendelse kræver en tom
  fejlliste og auditeres. Advarsler: intet kontaktgrundlag (fase 2), ukendt reklamebeskyttelse, reserveliste for viden.
- Viden: `knowledge_versions.audience` (`public`, `customer_docs`, `internal`). Kun salgsarbejdsrummet må sætte andet end
  `public`. Peter får `public` + `customer_docs`; `internal` kan ikke komme i en prompt (`build_system_prompt` afviser
  det). Kør `python -m scripts.seed_sales_knowledge` for at lægge FEATURES-fakta ind som udkast; operatøren godkender.
- Simulation: Peter mod en AI-kunde med persona; værktøjerne fra afsnit E §8 tilbydes, men kaldene gemmes som
  `would_call` og udføres aldrig. Delaccepter klassificeres med `sales-accepts-v1`; et citat, kunden aldrig sagde,
  kasseres. Alt er mærket "simuleret" og tæller aldrig i statistik.

## Kontaktgrundlag, kontaktpolitik og opkald (fase 2)

**Kontaktgrundlag.** På en virksomheds side under "Kontakter, kontaktgrundlag og opkald" registreres for hver kontakt
den fulde tekst, kontakten sagde ja til (anmodning eller samtykke til et AI-opkald), kilde og dokumentation. Det kan
trækkes tilbage. Koden og `docs/sales/demo-calls.md` holder fast i, at et AI-opkald kræver forudgående anmodning eller
samtykke – også til virksomheder (markedsføringslovens § 10, stk. 1). Uden gyldigt grundlag er svaret aldrig ALLOW.

**Kontaktpolitik** (`app/modules/sales/policy.py`): ALLOW / BLOCK / NEEDS_REVIEW med grunde. Blokerer ved ugyldig
kontakt, spærreliste (telefon/domæne/CVR), salgsarbejdsrummets frabedelser, lukket virksomhed, eksisterende kunde,
reklamebeskyttelse, manglende grundlag, for mange forsøg på tværs af kampagner, uden for vinduet, opbrugt budget,
stoppet kampagne og tilstand (`test` kun testnumre). Ukendt reklamebeskyttelse og ikke-godkendt manuskript giver
NEEDS_REVIEW. Uden CVR-adgang kan operatøren registrere et manuelt tjek (fx datacvr.virk.dk) på virksomhedens side.
Hver beslutning gemmes i `sales_policy_decisions`; den køres ved planlægning og igen lige før hvert opkald.

**Testopkald.** Sæt `SALES_OUTBOUND_MODE=test` og `SALES_TEST_NUMBERS=+45xxxxxxxx` på api og worker. Godkend et
manuskript, og brug "Testopkald til dit eget nummer" på virksomhedens side. Bekræftelsen gemmes som et `test`-grundlag
(30 dage) på nummeret; der oprettes en engangskampagne mærket "Test", og Peter ringer straks, hvis politikken
tillader det. Det er et rigtigt opkald via Vapi og salgsarbejdsrummets udgående nummer.

**Kampagner.** Kampagner → Ny kampagne (vindue, forsøg, budget som hårdt loft). Tilføj kontakter fra en virksomheds
side. Kampagnesiden viser forhåndsvisningen (ALLOW/BLOCK/NEEDS_REVIEW med grunde og omkostningsloftet: kontakter ×
forsøg × (4 kr. + 10 min × 2 kr.)). Start kræver, at du godkender loftet, og mindst én ALLOW. Pause og Stop (Stop
springer alle ventende kontakter over). Workeren ringer højst `SALES_MAX_CONCURRENT_CALLS` samtidigt.

**Idempotens.** Forsøget gemmes som "ringer" med en `dispatch_key`, før Vapi kaldes. Svarer Vapi slet ikke, markeres
forsøget "uvist" og ringes ikke op igen automatisk (tjek opkaldet hos Vapi). Peters manuskript låses på forsøget
(`sales_call_events`, type `assistant_snapshot`).

**Efter opkaldet.** Vapis `status-update` og `end-of-call-report` gemmes som hændelser. Udfaldet klassificeres som i
kundernes kampagner; delaccepterne (`sales-accepts-v1`) gemmes med kundens egne ord, og et citat, kunden aldrig sagde,
kasseres. Frabedelse → Dialogbots spærreliste + salgsarbejdsrummets frabedelsesliste; ventende forsøg til nummeret
springes over. Interesserede og "ring tilbage" bliver henvendelser med opgave i salgsarbejdsrummet. Opkald-fanen
viser alle forsøg (også ubesvarede og fejlede), transskript med talere, opsummering adskilt fra originalen,
delaccepter og hændelser; der kan søges i samtaletekst. Lyd: "ikke optaget" (fase 4). Tidsstempler pr. replik gemmes
ikke endnu.

**Interne kampagner er usynlige for kunder**: de ligger i salgsarbejdsrummet, men `/workspaces/{ws}/campaigns` viser og
styrer kun `kind=customer`.

## Peters værktøjer, tilbud, ordre, møder og statistik (fase 3)

**Peters værktøjer under opkaldet** (`app/modules/sales/tools.py`): `hent_tilbud`, `ledige_moedetider`, `book_moede`,
`opret_ordreudkast`, `send_bestillingslink`, `registrer_frabedelse`, `bed_menneske_foelge_op`. De tilbydes kun på
opkald i interne kampagner (også testopkald). Opkaldet findes ud fra Vapis opkalds-id i databasen – aldrig ud fra
metadata eller modellens argumenter – og alt tjekkes mod databasen. `book_moede` og `send_bestillingslink` kræver
`bekraeftet: true` (kundens udtrykkelige ja). Hver kørsel er én række i `action_runs` (connector `dialogbot_sales`) og
vises under "Peters handlinger" på opkaldet. Peters instruks siger, at han kun må love det, et værktøj har bekræftet.

**Møder.** Kør `python -m scripts.seed_sales_knowledge` (opretter bookingtypen "Intro-møde (30 min)" i salgsarbejdsrummet),
godkend åbningstider i salgsarbejdsrummet og slå online booking til (Booking → Indstillinger). Uden det svarer
`ledige_moedetider`, at en kollega finder en tid, og der oprettes en opgave. Ledige tider kommer fra
`bookings.slots()` (åbningstider, eksisterende bookinger og en tilsluttet kalender); Peter tilbyder højst to.
Et møde er `confirmed`, når bookingen er oprettet; aflyses bookingen, vises mødet som aflyst. Afholdt/udeblev
markeres på virksomhedens side.

**Tilbud og bestillingslink.** På virksomhedens side: "Opret tilbud" (gør-det-selv eller specialist). Beløbene kopieres
fra `billing/prices.py`; tilbuddet gælder 14 dage. "Send link" sender på e-mail (via outbox; status "sendt" først når
e-mailadapteren har leveret – med `EMAIL_ADAPTER=simulated` står der "simuleret") eller SMS (fra salgsarbejdsrummets
SMS-afsender). Når Peter sender, skal adressen matche kontaktens eller virksomhedens kendte e-mail/nummer; ellers venter
linket på, at du bekræfter adressen ("Kræver dig" og virksomhedens side), og der oprettes en opgave med frist 2 timer.
Et nyt link erstatter det gamle.

**Accept.** Kunden åbner `/tilbud/<token>`: pris ekskl. og inkl. moms, opsætning, minutpriser, ingen binding,
vilkårsversion. Accept kræver login eller oprettelse af konto (bekræftet e-mail). Accept opretter et nyt arbejdsrum
(eller bruger et, kunden administrerer), en aftale med tilbuddets priser (`reception_agreements.sales_offer_id`,
`setup_net_minor`) og sender videre til kortbetaling i Stripe. Status: kladde → sendt → accepteret. Virksomheden
bliver først "betalende kunde" ved arbejdsrummets første betalte Stripe-faktura (`invoice.paid`) – derefter blokerer
kontaktpolitikken den som eksisterende kunde. Specialist-opsætningen kommer på første faktura som linjen `setup_fee`.

**Statistik** (`/app/operator/salg/statistik`, `GET /operator/salg/stats?from&to&campaign`): hvert tal med tæller,
nævner og definition. Testkampagner (inkl. testopkald) og simulationer tælles aldrig. Omkostningen er leverandørernes
egen rapporterede pris i USD (estimat).

## Lyd, sletning efter frister og den registreredes rettigheder (fase 4)

**Optagelse er slået fra som udgangspunkt.** Vapi optager alle opkald, medmindre assistenten siger andet
(`artifactPlan.recordingEnabled` er som standard `true`, docs.vapi.ai/assistants/call-recording). Peters assistent
sætter derfor altid feltet: til kun når `SALES_RECORDING_STORAGE=supabase` (kræver `SUPABASE_URL` +
`SUPABASE_SERVICE_ROLE_KEY` og en **privat** bucket `SALES_RECORDING_BUCKET`) OG kampagnen (eller testopkaldet) har
"Optag samtalerne". Så siger Peter i åbningen: "Samtalen bliver optaget til kvalitetssikring – sig til, hvis du ikke
ønsker det." Vil kunden ikke optages, kalder Peter `stop_optagelse`: filen hentes aldrig, og Vapi bedes slette opkaldet
(`DELETE /call/{id}`, som sletter optagelserne). Vapi har ingen dokumenteret måde at stoppe en optagelse midt i
samtalen.

**Hentning og afspilning.** Efter opkaldsrapporten henter workeren lyden med den private nøgle fra
`GET /call/{id}/mono-recording` (svarer med en 302 til et kortlivet signeret link, docs.vapi.ai/assistants/retrieve-call-artifacts)
og gemmer den som `sales/calls/<call_id>.<wav|mp3>` i bucketen. Opkaldssiden afspiller via et signeret link, der lever
højst 10 minutter, med hastighedsvalg. Hver afspilning og eksport logges i `sales_media_access_log`. Eksport kræver
`users.can_export_media` (sættes direkte i databasen for den enkelte operatør).

**Frister** (worker, dagligt efter kl. 3, også når kanalen er slået fra): lyd slettes efter
`SALES_RETENTION_AUDIO_DAYS` (30), transskript anonymiseres efter `SALES_RETENTION_TRANSCRIPT_DAYS` (90) – hver replik
bliver "[slettet]", og Vapi bedes slette sin kopi – og opsummeringen ryddes efter `SALES_RETENTION_SUMMARY_DAYS` (365).
Opkaldsrækken (tid, varighed, udfald) og auditsporet bevares. Kun interne salgsopkald berøres.

**Indsigt og sletning** (fanen "Indsigt og sletning", `POST/GET /operator/salg/data-requests`): indsigt samler alt om et
telefonnummer, en e-mail eller et CVR-nummer (virksomheder, kontakter, fakta, kontaktgrundlag, opkald med transskript,
tilbud, beskeder, spærringer) som JSON. Sletning anonymiserer transskripter og opsummeringer, sletter lyd (også hos
Vapi), sletter kontakterne og – for et CVR-nummer – virksomhedens research; nummeret/CVR'et spærres, så vi ikke
kontakter igen. Indsigelse spærrer. Telefonnummeret står fortsat i opkaldsloggen af hensyn til afregning og spærring.

**Privatlivstekst.** Udkast i `docs/sales/privatliv-udkast.md` – skal godkendes af ejeren, før det kommer på /privatliv.

## Hvad er mock / kræver konfiguration / ikke implementeret

| | |
|---|---|
| Mock | Demo-data uden Google-nøgle; `AI_PROVIDER=fake` i test. |
| Kræver konfiguration | `GOOGLE_PLACES_API_KEY` (rigtig søgning), `SALES_WORKSPACE_ID` + AI (research og simulation), `CVR_USERNAME/PASSWORD` (reklamebeskyttelse), `SALES_OUTBOUND_MODE=test` + `SALES_TEST_NUMBERS` + Vapi + et udgående nummer i salgsarbejdsrummet (testopkald), bookingtype "Intro-møde" + åbningstider + online booking i salgsarbejdsrummet (møder), `EMAIL_ADAPTER=resend` (rigtige mails med bestillingslink), SMS i salgsarbejdsrummet (link på SMS), `STRIPE_SECRET_KEY` (kortbetaling efter accept). |
| Lyd | `SALES_RECORDING_STORAGE=supabase` + Supabase-nøgler + privat bucket; ellers optages intet. Eksport kræver `users.can_export_media`. |
| Ikke implementeret | Åbne spørgsmål oprettes af `bed_menneske_foelge_op`, men har endnu ingen egen kø-side; /privatliv-teksten er et udkast; Vapis egne opbevaringsregler styres i Vapi. |

## Kendte begrænsninger

- Højst 60 resultater pr. Google-forespørgsel; delområder giver bedre, ikke fuld dækning.
- Google-felter må kun gemmes i begrænset tid; uden nøgle kan de ikke genopfriskes og nulstilles derfor.
- CVR er kun berigelse; uden legitimation er reklamebeskyttelse ukendt.
- Telefon-OTP på "ring mig op" er ikke en del af planen.
- Dagsloftets tælling af genopfriskninger ligger i processens hukommelse (søgejob tælles i databasen).
- Priser i overslaget er ikke genverificeret mod Googles prisliste.
