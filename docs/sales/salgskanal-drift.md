# Dialogbots interne salgskanal – drift

Status: **fase 1 implementeret** (søgning, sikker research, profil, manuskript, simulation, admin). Fase 2–4 (kontaktpolitik,
kampagner, testopkald, tilbud/ordre, møder, statistik, lyd, retention) er **ikke implementeret**. Analyse og plan:
`docs/sales/intern-salgskanal.md`. Kun platformsoperatører har adgang (`/app/operator/salg`, API `/api/v1/operator/salg/*`).

## Tilstande (`SALES_OUTBOUND_MODE`)

| Værdi | Hvad virker |
|---|---|
| `off` (standard) | Kun statussiden `GET /operator/salg`. Alle andre ruter svarer 501 `sales_channel_off`; workeren kører ingen søgejob. |
| `research` | Søgning, import, research af hjemmesider, profil, manuskript, integrationsregister. |
| `simulation` | Som `research` + simulerede samtaler. Anbefalet til staging og til at prøve kanalen af. |
| `test`, `live` | Accepteres af konfigurationen (`live` kræver Vapi og `TELEPHONY_PROVIDER=live`), men **der findes ingen opkaldskode i fase 1** – intet ringes op. |

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
  et felt uden værdi fjerner hele sætningen. Validering: ingen pladsholdere, kun beløbene 2.495/4/5.000 kr. fra
  `billing/prices.py`, integrationsstatus fra registret, fakta med gyldig kilde, funktioner fra godkendt viden,
  kalenderbooking kun når integrationen er AKTIV, reklamebeskyttede virksomheder afvises. Godkendelse kræver en tom
  fejlliste og auditeres. Advarsler: intet kontaktgrundlag (fase 2), ukendt reklamebeskyttelse, reserveliste for viden.
- Viden: `knowledge_versions.audience` (`public`, `customer_docs`, `internal`). Kun salgsarbejdsrummet må sætte andet end
  `public`. Peter får `public` + `customer_docs`; `internal` kan ikke komme i en prompt (`build_system_prompt` afviser
  det). Kør `python -m scripts.seed_sales_knowledge` for at lægge FEATURES-fakta ind som udkast; operatøren godkender.
- Simulation: Peter mod en AI-kunde med persona; værktøjerne fra afsnit E §8 tilbydes, men kaldene gemmes som
  `would_call` og udføres aldrig. Delaccepter klassificeres med `sales-accepts-v1`; et citat, kunden aldrig sagde,
  kasseres. Alt er mærket "simuleret" og tæller aldrig i statistik.

## Hvad er mock / kræver konfiguration / ikke implementeret

| | |
|---|---|
| Mock | Demo-data uden Google-nøgle; `AI_PROVIDER=fake` i test. |
| Kræver konfiguration | `GOOGLE_PLACES_API_KEY` (rigtig søgning), `SALES_WORKSPACE_ID` + AI (research og simulation), `CVR_USERNAME/PASSWORD` (reklamebeskyttelse). |
| Ikke implementeret (fase 2–4) | Kontaktpolitik (`ALLOW/BLOCK/NEEDS_REVIEW`), kontaktgrundlag, spærreliste, interne kampagner, testopkald, opkaldsliste/transskript, Peters rigtige værktøjer, tilbud/ordre/acceptside, møder, statistik, lyd, retention, indsigt/sletning. "Må ringes op" viser i fase 1 kun kendte blokeringer, aldrig "ja". |

## Kendte begrænsninger

- Højst 60 resultater pr. Google-forespørgsel; delområder giver bedre, ikke fuld dækning.
- Google-felter må kun gemmes i begrænset tid; uden nøgle kan de ikke genopfriskes og nulstilles derfor.
- CVR er kun berigelse; uden legitimation er reklamebeskyttelse ukendt.
- Telefon-OTP på "ring mig op" er ikke en del af planen.
- Dagsloftets tælling af genopfriskninger ligger i processens hukommelse (søgejob tælles i databasen).
- Priser i overslaget er ikke genverificeret mod Googles prisliste.
