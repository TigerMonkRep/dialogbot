# Design-noter – e2e-privat PB (apps B), 2026-11-10

Til UI/UX-engineer. Gælder appsene Ring for mig, Ønskelister, Kalender, Pakker, Madplan, Regninger, Læge & tandlæge,
Pakkeliste, Rejser og Kæledyr. Observeret i browseren mod :3400 → :8400 (mobil-390 først) og i API-svarene.
Fejl står i qa/findings/F-PB-*. Gentager ikke notes-PA.md: eksemplet i Butikken (PA 7), kept-siden viser ikke data
(PA 11) og «Ret» kun i chatten (PA 13) gælder også for mine apps.

## Plan og pris – den 60-årige skal ikke betale for meget
1. **Ring for mig siger «Plus og Familie»** (F-PB-02). Butikkens bund-linje `apps.planIncluded` («Med i Plus og Familie.»), `apps.planTextTrial` og `apps.planTextEnded` er hårdkodede. For Ring for mig er Basis nok, og radio-listen viser også Basis. Tekst og valg siger altså to forskellige ting. Byg linjen ud fra `included_in`.
2. **Badget «Plus · Familie»** og linjen «Med i Plus og Familie» står begge på samme kort i Butikken. Ét af dem er nok.

## Slå til / slå fra
3. **Ingen kvittering ved «Slå til igen»** (F-PB-03). Arket lukker med det samme. Den 60-årige ved ikke, om det virkede, og ser «Trin 1 af 3» igen, selvom hendes regninger står lige nedenunder (samme som F-UX-04). Forslag: toast «Regninger er slået til igen – dine 3 regninger er her stadig».
4. **Slå fra af Ring for mig slår også Læge & tandlæge og Kæledyr fra.** DisableSheet viser det korrekt («… slås også fra»), men «Fortryd» i toasten er den eneste vej tilbage, og den forsvinder efter 8 s. Overvej at vise de afhængige apps i Mine apps som «Slået fra sammen med Ring for mig».

## Apps uden «dine ting» på app-siden
5. **Pakkeliste, Ønskelister og Ring for mig** har ingen panel (coverage §3.9). App-siden viser kun opsætning og «Slå fra». Brugeren kan ikke se sine pakkelister, ønskelister eller opkald fra appen. Forslag: én linje «Dine pakkelister (2) →», der linker til Opgaver filtreret på appen.
6. **Madplan-panelet** viser kun præferencerne (antal, undgå, kan lide). Den gemte madplan og indkøbslisten er ikke synlige fra appen. Samme forslag som 5.

## Små ting
7. **Regninger: «Fjern» uden fortryd.** Et forkert tryk på 390 px sletter regningen med det samme. Kort-knapperne «Fjern» og påmindelses-vælgeren står tæt. Giv «Fjern» en fortryd-toast (som slå fra har).
8. **Læge & tandlæge: DELETE af ukendt type svarer 204** (`/health-contacts/hjerteklinik`). Det er ufarligt, men inkonsekvent med de andre apps (404). S3.
9. **Kommer snart (Pakker, Rejser):** Siden er ærlig («Appen er ikke klar endnu …», «Giv mig besked» huskes efter reload), der står ingen pris og ingen «Slå til», og /privat/pakker (egen rute) siger også «kommer snart». Godt – ingen ændring.
10. **Kæledyr: eksemplet i Butikken bruger «1. marts»**, men assistenten gemmer kun datoer, den kan tolke. Et eksempel med år («1. marts 2027») mindsker risikoen for, at datoen bliver gættet forkert.

11. **Ring for mig-opgave:** «Næste skridt: Godkend opkaldet» + knappen «Se forslaget og godkend» er et ekstra tryk, før man ser, hvad Peter må sige. For en 60-årig er det fint; men «Tidspunkt: –» på kortet, når brugeren skrev «torsdag efter kl. 15», ser ud som om Peter ikke hørte det (vinduet står i titlen, ikke i feltet).

## Test-harness (ikke design, men til holdet)
- Fake-modellen svarer «Klaret.» efter ethvert værktøjskald, også når værktøjet svarer «Ikke gemt: brugeren har ikke sagt ja endnu» (madplan) eller «Der er ingen gemt tandlæge» (læge). I QA-stakken ser det ud, som om noget er gjort, uden at noget er sket. Det er ikke en produktfejl med en rigtig model, men demoer på fake-modellen vil lyve. Mine tests asserter derfor altid på data.
- Butikkens eksempelsætninger for Regninger og Kæledyr rammer ikke fake-modellens regex («Mind mig om bilforsikringen …» bliver til en påmindelse, «1. marts» bliver ikke tolket). Testene bruger fake-formuleringer, se fil-headerne.
