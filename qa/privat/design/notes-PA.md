# Design-noter – e2e-privat PA (apps A), 2026-11-10

Til UI/UX-engineer. Observeret i browseren mod :3400 → :8400 (mobil-390 først) og i API-svarene, som UI'et viser ordret.
Det er ikke fejl, der blokerer et flow. Fejl står i qa/findings/F-PA-*.

## Tekst og tal (backend-tekster, som UI viser ordret)
1. **«1 abonnementer»**: `subs_app.overview` bøjer ikke ental («1 abonnementer – 199 kr. om måneden»). Det samme mønster bør tjekkes i «1 fest.», «1 gruppe.», «9 faste opgaver».
2. **Fitness-resumé uden punktum**: «Mål: 5 km i maj Denne uge: 0 træninger af 3 planlagte.» Linjeskiftet forsvinder i panelet (`whitespace-pre-line` virker kun, hvis summary har `\n`; overview-summary er sat sammen med mellemrum). Læses som én lang sætning.
3. **«Mette betalte 1.200 kr.»**: Fælles udgifter skriver brugerens fornavn i 3. person i brugerens egen chat. «Du betalte» er varmere og tydeligere for en 60-årig.
4. **Gruppenavn med lille forbogstav**: «Gemt i «sommerhuset»» / listen «Udgifter: sommerhuset». Brug stort forbogstav, som de andre apps gør («Idas 10-års fødselsdag», «Vaskemaskine»).
5. **Opsigelsesbrev «Hej Telia»**: Brevet til en virksomhed starter med «Hej <firmanavn>». «Til Telia» eller «Kære Telia» passer bedre til et formelt brev.
6. **Basis-bruger i PlanSheet**: Teksten `apps.planTextEnded` siger «Din prøveperiode er slut – vælg en plan», også til en Basis-kunde, der ikke er i en udløbet prøveperiode. Brug en tekst til «du har Basis – appen er med i Plus og Familie».

## Struktur
7. **Eksemplet mangler i Butikken**: App-siden i Butikken viser «Hvad den gør», trin og tilladelser, men ikke eksempelsætningen («Sig det til Peter»). Eksemplet er det, der får en 60-årig til at forstå appen på 3 sekunder. Overvej én eksempel-chip i stedet for trin-listen (mindre tekst, ikke mere).
8. **«Du skal bruge» er skjult på mobil i Butikken**: `Needs` står i `hidden xl:block` i ShopAction og kun i AboutApp (ikke-compact). Tjek, at det ikke vises to gange på desktop og nul gange på mobil for apps med `needs`.
9. **Håndværker i demo/QA uden Google-nøgle**: «Jeg fandt ingen male med et telefonnummer i nærheden» (fake-modellens bøjning, men den tomme tilstand er produktets). Den tomme tilstand bør tilbyde «Skriv navn og nummer på en, du kender» som knap, ikke kun som tekst.
10. **Slet data: overskrift og knap siger to forskellige ting**: Overskriften er «Slet appens data», knappen «Slet data», bekræftelsen «Ja, slet». Det er tre ord for samme handling. Vælg ét.
11. **Kept-siden viser ikke dataene**: «Dine data er gemt … Det, den har gemt, er her stadig», men siden viser ingen af dem (husstandspanelet skjules, når appen er slået fra). En bruger, der vil se sine gemte garantier, før hun sletter, kan ikke det. Overvej en skrivebeskyttet liste.
12. **Garanti og Fælles udgifter i samme chat**: «Del indkøbslisten med Anna» uden at stå på listen foreslår den senest oprettede liste («Udgifter: sommerhuset» / «Flytning: Odense»). Forslaget navngiver listen, så brugeren kan sige nej, men det er forvirrende. Lad forslaget vælge den liste, hvis titel matcher «indkøbsliste», eller spørge «Hvilken liste?».

## Konsistens mellem apps
13. **«Ret» findes kun i chatten**: Husstandspanelerne har kun «Fjern» (og «Kopiér»). Fødselsdage og Bil har formularer. For en 60-årig er det inkonsekvent, at nogle apps kan rettes på skærmen og andre ikke kan. Mindst: en hjælpelinje «Vil du rette noget? Skriv det til Peter» ved hvert kort.
14. **Bil & syn har ingen «Fjern»**: Nummerplade og datoer kan kun tømmes ved at slette feltindholdet og gemme. Der er ikke noget «Fjern bilen».
15. **Tom tilstand uden eksempel (apps med panel)**: Efter ux-audit #7 viser apps med panel den gule trin-linje + panelet + «Spørg Peter», men eksempelsætningen («Sig fx …») står kun der, hvor panelets tomme resumé tilfældigvis citerer den (Fest, Flytning, Håndværker). Abonnementer («Ingen abonnementer endnu. Fortæl Peter, hvad I betaler for.»), Bil & syn, Fødselsdage og Garanti viser intet eksempel. «Spørg Peter» udfylder det i chatten, men på skærmen ser brugeren ikke, hvad hun kan sige. Scenarierne PC-APP-*-03 forventer «eksempel-chip og Spørg Peter». Forslag: vis `apps.sayLike` under knappen også i panel-layoutet, når panelet er tomt.
16. **Butikken skjuler apps, der er slået til**: «Alle 18» i stedet for 21. Det er fint, men en bruger, der leder efter «Delte lister» i Butikken, finder den ikke. Et lille «Slået til – se Mine apps»-kort eller en tæller ville hjælpe.
17. **Bil-formularen kan overskrive det, man er ved at skrive**: CarPanel kalder `setForm(data)`, når data kommer. Taster man, før panelet har hentet, nulstilles feltet, og «Gem» gemmer tomt (set i Playwright på 390 px). Det er sjældent for mennesker, men på langsom mobil-forbindelse er det muligt. Sæt kun formularen første gang, eller deaktivér felterne, mens der hentes.
