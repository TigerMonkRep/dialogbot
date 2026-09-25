# Dialogbot — eksport og dokumentation før designgodkendelse

Udarbejdet 24. september 2026 efter den vedhæftede Pasted text.txt. Rapporten er læst fra dens lokale kopi og er ikke ændret. Ingen direkte inspektion af Stitch-projektet er udført her.

## Resultat af rapportgennemgangen

- Der er 129 unikke kravrækker, alle mærket Complete. Denne optælling er korrekt; den fastslår ikke, at alle skærme og forbindelser virker.
- Henrik-eksemplets kronologi og behandlingen af en ufaktureret tvist er nu beskrevet korrekt i rapporten. De gemte skærme er ikke medsendt til kontrol.
- Rapporten leverer ingen downloadlinks, kildefiler eller skærmbilleder. Dens handoff består af beskrivelser af ruter, designværdier og integrationer.
- M01–M04 bruger alle SCREEN_100 som mobilreference; M05–M07 henviser til andre adminskærme uden præcise visningstilstande. Genbrug er tilladt, men dækningen kræver konkret dokumentation.
- H01/M06 beskrives som support, mens det demonstrerede forløb omhandler B04/M04-tvistbehandling. Et normalt supportforløb er derfor ikke demonstreret i teksten.
- Der er nye konkrete hosting-, sikkerheds-, selskabs- og compliancepåstande, som rapporten ikke dokumenterer. Gennemgangen tager ikke stilling til den juridiske korrekthed af disse påstande; de kan ikke bruges som verificerede produktoplysninger på dette grundlag.

## Prompt til Stitch

Dialogbots seneste rapport har 129 unikke kravrækker, alle mærket Complete. Nu skal resultatet kunne kontrolleres direkte i de eksisterende artefakter. Lever en konkret design- og prototypeeksport med dokumentation. Bevar projektet og den eksisterende kravliste.

1. Eksportér de faktisk gemte skærme og deres tilgængelige kildefiler/aktiver, helst samlet som en downloadbar ZIP, hvis værktøjet understøtter det. Medtag projektets eksisterende prototypeforbindelser, hvis de kan eksporteres. En eksport skal komme fra de gemte artefakter; generér ikke en ny erstatningsprototype og præsenter den som eksport.

2. Lever et skærmindeks med krav-ID, gemt skærmreference, faktisk rute eller prototypeindgang, præcis fane/tilstand, viewport og filnavn. Fælles responsive filer er tilladt, men deres forskellige visninger skal kunne genfindes. Fortæl, hvis de tidligere SCREEN-ID'er er blevet ændret, og giv den aktuelle mapping.

3. Vedlæg skærmbilleder fra de faktisk gemte visninger ved 1440px og 390px for de nedenstående kontrolområder. Hvis screenshot- eller filgenerering ikke understøttes, angiv præcis hvilken begrænsning der gælder, og lever de faktiske kilder/artefaktlinks, du har adgang til. Opfind ikke downloadlinks eller eksportfiler.

4. Dokumentér disse områder ved at åbne deres tilstande og afprøve prototypehandlingerne:

- M01–M07: Vis hver af de syv operatørfunktioner på mobil. SCREEN_100 er angivet for M01–M04 og omtales samtidig som “Mobilapp, Push & Døgnvagt”. Vis den konkrete operatørtilstand og vejen til den. En fælles fil kan bruges; en generisk mobilapp-skærm dokumenterer ikke alle syv funktioner.
- H01/M06: Vis en almindelig supportsag fra kundeoprettelse med bilag til operatørtildeling, intern note, kundesynligt svar og kundens beskedtråd. Tvistforløbet B04/M04 er en anden opgave og dækker ikke alene dette.
- M05/M07: Vis den redigerbare skabelon med version/publicering samt den filtrerbare operatørlog. Angiv de præcise paneler, hvis de er indlejret i andre adminskærme.
- P04/P05/P07/P08/P09: Vis den faktiske navigation, fungerende eksempelberegner, hjælpesøgning/artikel, kontaktformularens fejl/succes og de offentlige dokumentvisninger, inklusive cookies. En henvisning til landing page, widget eller privatlivsindstillinger er kun tilstrækkelig, hvis det krævede indhold og handlingerne faktisk findes dér.
- K04/BK11: Vis tilbudsredigering med start/slut og status samt ressource-/kapacitetsstyring med konflikt og ikke-understøttet tilstand.
- C03/W09: Vis kontaktimportmulighederne ud over CSV, inklusive dokument-/PDF-gennemgang, API og understøttet read-only database; vis separat callbackaflysning/præferencer og kalenderaftalens W13-administration.
- E01/E04/E07: Vis de faktiske mail-/beskedvarianter. E01 kræver bekræftelse, nulstilling og invitation. E04 skal også dække henvendelse/callback. E07 skal omfatte bookinganmodning, bekræftelse, påmindelse, ændringsforslag, flytning, aflysning, ejeropmærksomhed og leveringsfejl.

5. Fjern eller mærk udokumenterede påstande fra den seneste rapport/UI som afventende implementering eller godkendelse: Equinix Ballerup-hosting, CVR, NIS2-/DPA-overholdelse og Argon2id-implementering. Brug ikke et ikke-bekræftet domæne som platformens faktiske afsender; brug eksempelvis sikkerhed@dialogbot.example i demoen. Mærk valgte gyldighedsfrister som konfigurerede demoeksempler, hvis der ikke foreligger en godkendt politik. Vis “nummerbekræftelse med engangskode” i callbackflowet frem for en udokumenteret påstand om to-faktor-login.

6. Kontrollér de rapporterede rettelser i de gemte visninger: parkeringsopgaven er fuldført før besigtigelsen, datoer og rapportperioder stemmer, ufaktureret DISP-1049 afvises uden fejlagtig kreditnota, fravalg stopper fremtidige forsøg uden at slette tidligere forbrug, og kalendergenopretning viser genforbindelse før afstemning. Afstem G01's “4 af 7” og G05's “86 %” med deres faktiske opgaver/omfang, eller ret dem.

For hver afprøvet overgang: angiv startartefakt/tilstand, konkret kontrol, udført handling, destinationsartefakt/tilstand, observeret resultat og vedlagt bevis. Et screenshot viser udseendet; det beviser ikke alene en fungerende overgang. Hvis interaktion ikke kan testes, markér den Uverificerbar og forklar begrænsningen.

Findes en påstået funktion ikke, ret kun den konkrete mangel og medtag før/efter-evidens. Er skærmen utilgængelig for inspektion, må du ikke konkludere, at den mangler. Tilføj ikke nye moduler eller nye forretningsregler.

Afslut med:
- De faktiske downloadbare filer eller tilgængelige artefakter.
- Skærmindeks og den udførte kontrol.
- Kun de krav, hvis status ændres, med begrundelse; bevar det fulde indeks i eksporten.
- Resterende eksport-/inspektionsbegrænsninger og udestående rettelser.

Hold design, prototypeinteraktion og produktionsimplementering adskilt. Giv ikke endnu en generel “129/129 færdig”-erklæring som erstatning for leverancerne. Start med at hente og åbne M01–M07's eksisterende mobilvisninger, og fortsæt derefter gennem kontrolområderne.

