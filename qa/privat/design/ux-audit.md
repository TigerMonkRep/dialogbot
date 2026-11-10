# Privat: UX-, design- og art direction-audit (fase 1)

Dato: 2026-11-10 · Af: ui-ux-engineer, som også har haft designerens og art directorens tjeklister (`.claude/agents/designer.md`, `art-director.md`).
Stak: web :3400 / API :8400 (falsk Stripe og Vapi, `AI_PROVIDER=fake`). Ingen produktkode er ændret.

- **Skærmbilleder:** `/home/claude/pd-results/UX/shots/` (88 stk., `m-` = 390 px, `d-` = 1440 px). Et udvalg ligger i `qa/evidence/privat-ux/`.
- **Script:** `/home/claude/pd-results/UX/scripts/shoot.mjs`, faser `public | owner | plus | screens | guest`. Fuldsideskud udvider viewporten, fordi Privat-skallen scroller inde i `main`.
- **Måling:** `qa/evidence/privat-ux/a11y.json` – ord pr. skærm, antal orange primærknapper og mål under 44 px.
- **Mockups:** `qa/privat/design/mockups/*.html` (før → efter, uafhængige af appens build).
- **Fund:** `qa/findings/F-UX-01 … F-UX-08`.

---

## 0. Konklusion

Privat er **visuelt på mærket**: orange tema, Outfit/Inter, 2 px blæk og blok-skygge. Den er også **konsistent på tværs af apps**: alle 14 app-sider bruger samme app-kit (`AppPage` i `components/privat/apps.tsx`). Det skal vi beholde.

Problemet er det, Fürster selv siger: **for meget på hver skærm, og for mange ting, der kæmper om at være "den ene"**.

| Skærm (390 px) | Ord | Orange primærknapper | Sektioner | Den ene ting i dag |
|---|---|---|---|---|
| Min dag | 326 | 1 (+ 14 gule app-kort) | 6: installér, Peter, Din tur, Dine apps, Dine opgaver + 4 filtre, Dit råderum | Uklar. Installér-kortet står over Peter. |
| Samtale | 306 | 1 | Fulde ønskekort med 200 px tomme billeder midt i chatten | Peter |
| Butikken | 381 | 0 | Forslag, 4 kategorier, 21 apps, både slået til og fra | Uklar |
| Mine apps | 217 | 1 | Opsætningskort + 14 rækker, 11 af dem med gul «Trin 1» | Opsætningskortet |
| App i brug (Kalender) | 161 | **4** | Trin-kort, «Sig det til Peter», indstillinger, «Den får lov til», Slå fra | Uklar |
| Konto | 250 | 2 | **10 kort** | Uklar |
| Folk | 58 | 1 | 2 grupper + «Ny gruppe» | **Tydelig: det er forbilledet** |

Ordtallet er synlig tekst i `main` (a11y.json). **Mål for fase 2:** højst 120 ord og én orange knap pr. skærm, over folden på 390 × 844.

---

## 1. Skærm for skærm

Hver skærm er gennemgået med de samme spørgsmål: Hvad er den ene ting? Hvad er for meget? Er der én primær handling? Følger den byggevejledningen og Privat-temaet? Holder tommelfinger-ergonomien og 44 px-målene? Hvordan er tilgængeligheden? Er tilstandene (tom, fejl, indlæsning) på plads?

### 1.1 /privat landing (`web/src/app/privat/page.tsx`, `components/privat/public.tsx`)
- **Den ene ting:** «Prøv gratis i 14 dage».
- **For meget:** Hero har tre knapper: Prøv gratis, Prøv på 2 minutter og Download app. På mobil bryder headeren i to rækker (logo + Erhverv/Privat-skift, derefter DA + Log ind), så selve indholdet først starter ved 170 px. Priserne vises som tre fulde plankort, hver med 4-5 punkter.
- **Godt:** Demo-kortet med «Ja, ring» → «Ordnet» viser før → efter (byggevejledningens regel 4), og orange er tydeligt Privat.
- **A11y:** OK. Fokusrækkefølgen følger det visuelle.
- **Ændringer:** Én primær og én sekundær knap. «Download app» rykker ned i en sidefod-sektion. Headeren samles på én række ved 390 px: DA ind i menuen, «Log ind» som ikon og tekst.

### 1.2 /privat/start funnel (`app/privat/start/privat-steps.tsx`)
- **Godt:** Byggevejledning i ren form: trin-tal, ét spørgsmål og én knap. Fortsæt sådan.
- **For meget:** Trin 1 har 8 valg *og* «Hvad skal din assistent hedde?». Navnet hører hjemme efter købet (Konto).
- **Tilstande:** Den deaktiverede «Videre» (lys orange) har for lav kontrast til at blive læst som tekst. Det er acceptabelt for en deaktiveret knap, men vis hellere en tæller («Vælg mindst én»).

### 1.3 Checkout-retur (/privat/konto?abonnement=ok)
- **Problem:** Brugeren lander på hele Konto-siden med 10 kort. Bekræftelsen er en grøn bjælke plus et kort, der siger «Plus-rettigheder» på en Basis-trial (**F-UX-01, S1**).
- **Ændring:** Retur skal gå til **Min dag**, med én gul «her er du»-bjælke: «Din prøveperiode kører – 14 dage. Hvad skal jeg klare først?». Konto er ikke et sted, man skal lande.

### 1.4 Min dag (`components/privat/day.tsx` DayPage)
- **Den ene ting:** «Skriv, hvad du skal have klaret» (Peter).
- **For meget:**
  - (1) Installér-kortet («SIDSTE TRIN … Download app … Åbn siden på din telefon») står **over** Peter ved første besøg, også for en gæst uden plan, og skubber composeren under folden.
  - (2) «Din tur» vises tomt («Intet venter på dig, 0 opgaver»).
  - (3) «Dine apps»: 14 gule kort med «Trin 1 af 3 – fortsæt opsætningen» (**F-UX-04**). Gul bliver støj og er ikke længere «her er du».
  - (4) Opgaver med fire filterchips, hvilket gentager Opgaver-fanen.
  - (5) «Dit råderum» med to progress-barer og en prisforklaring. Det hører til Konto.
- **Byggevejledning:** Bryder «én handling pr. trin». Blok-skygge sidder på tre kort.
- **Ergonomi:** Composeren står midt på skærmen. På mobil bør den sidde i bunden over tab-baren (tommelfingerzone), som i Samtale.
- **Desktop:** App-båndet stikker ud over kanten (F-UX-08c).
- **Mockup:** `mockups/dag.html`.

### 1.5 Opgaver og opgave-detalje (`components/privat/tasks.tsx`, `cards.tsx`, `wishes.tsx`)
- **Liste:** God og rolig. Hver række har dog både en status-pille («I gang») og en type («Liste»). Gruppe-overskriften siger allerede «I gang», så pillen kan gå. «Påmindelse i morgen kl. 17.00 · Torsdag kl. 17.00 · Assistenten minder dig» siger det samme tre gange.
- **Detalje:**
  - Kortet «Næste skridt» med *Formål / Tidspunkt «–» / Hvem gør noget / Forbrug «Med i prøveperioden»* er intern bogføring. Fjern det for lister og påmindelser, og behold det kun for opkald, hvor forbruget betyder noget.
  - Ønskelisten: «Næste skridt: Del ønskelisten», men «Deling»-knappen står **nederst** efter tre 200 px tomme billedfelter. «Delt med –» viser en tankestreg, når listen ikke er delt.
  - Gæsten får ejerens næste skridt (**F-UX-02**). Den neutrale designtema-header er Erhverv-blå (**F-UX-06**).
- **Ændring for ønskeliste (ejer):** titel → «Del med …» som den ene orange knap øverst → kompakte ønskerækker (64 px thumbnail, uden pladsholderbillede) → «Tilføj ønske» som sekundær knap.
- **Ændring for gæst:** titel → «Fra Mette» → rækker med «Jeg køber den». Ingen opgave-metadata, ingen historik og ingen «Tal om opgaven» uden plan.

### 1.6 Samtale (`components/privat/chat.tsx`)
- **Godt:** Composeren sidder i bunden. Bobler i blæk og orange-panel.
- **For meget:** Lister og ønskelister indsættes som fulde kort i chatten. En ønskeliste med tre ønsker fylder 900 px. Pakkelisten viser «Mette Hansen tilføjede …» under hvert punkt på en liste, der ikke er delt.
- **Ændring:** I chatten vises et kompakt resultatkort («Ønskeliste · 3 ønsker · Åbn») plus «Del»-chip. Hele listen ligger på opgavesiden.

### 1.7 Butikken og app-detalje (`components/privat/apps.tsx`)
- **Butikken:**
  - Viser både apps, der er slået til («✓ Slået til»), og nye apps. Det er 21 rækker og 381 ord, og det gentager Mine apps. Butikken bør kun vise det, du **ikke** har.
  - Ikonfliserne har fem forskellige baggrunde (mint, gul, blæk, orange, lys orange). Det er en regnbue, og brand.md siger «hvide ikoner på accent-flise».
- **App-detalje:**
  - Rækkefølgen «Hvad den gør → Sig det til Peter → Sådan virker den (3 gule tal) → Den får lov til → sticky «Slå til»» er tæt på byggevejledningen.
  - «Du skal bruge» mangler dog før «Sådan virker den» (brand-regel 2).
  - «Hvad den gør» er 50-60 ord, og 25 er nok.
  - «‖»-glyfen er et fejltegn (F-UX-08b).
- **Ærlighed:** «Kommer snart» vises med «Giv mig besked» i stedet for «Slå til». Det er korrekt (Rejser, Pakker).
- **Mockup:** `mockups/butik-app.html`.

### 1.8 Mine apps og apps i brug (`components/privat/apps.tsx` AppPage; ruterne `/privat/apps/<key>` samt de gamle `/privat/regninger`, `/foedselsdage`, `/bil`, `/pakker`)
- **Konsistens:** Alle apps bruger samme kit (trin-kort, «Sig det til Peter», «Indstillinger og dine ting», «Den får lov til», «Slå fra»). Det beholdes.
- **For meget pr. app:** Fire veje til den samme handling: «Spørg Peter», «Trinnet er klaret», «Spring opsætningen over» og «Sig det til Peter»-boblen, og derudover en formular med sin egen orange «Gem».
  - Kalender har **4 orange knapper**: Spørg Peter, Forbind, Forbind og Lav privat link.
  - Fødselsdage står på «Trin 1 af 3», selv om Sofie er gemt (F-UX-04).
- **Ændring:** Når appen har data, er *dine ting* det første på siden (Sofie · 3. dec · om 22 dage). Opsætnings-trinnet bliver en tynd gul linje («Trin 2 af 3: …»), og der er én orange knap. Formularer får sekundærknapper. «Den får lov til» og «Slå fra» samles i en «Om appen»-fold nederst.

### 1.9 Folk og grupper (`components/privat/people.tsx`)
- **Liste:** Forbilledet: kort, én primær knap («Ny gruppe») og en tryghedslinje.
- **Ret gruppen:** Rækkefølgen Navn → Medlemmer → «Lad dem melde sig selv» (orange) → «Importér fra iPhone (.vcf)» med trin er god.
  - Men «invitér» som verbum mangler i sidens top. Folk-fanen siger ikke, *hvorfor* man laver en gruppe.
  - Desktop har ingen «Folk» i topnavigationen; den ligger kun i avatar-menuen. Mobilfaner og desktop-nav bør være de samme 5 punkter.
- **Delingsark:** Blander «Del med en gruppe» og «Send et link» og tilbyder at gøre en ønskeliste til «Fælles liste».
  - Medlemsrollen vises som «kan ændre» for en ønskeliste-gæst (**F-UX-03**).
  - **Ændring:** Arket starter med det, brugeren deler (ønskeliste). Derefter følger tre store valg (Familien · Fodboldholdet · Send link), én «Send»-knap og en SMS-forhåndsvisning.
- **Mockup:** `mockups/folk-inviter.html`.

### 1.10 Invitation-modtager (`app/privat/invitation/[token]/page.tsx`)
- **Godt:** Én primær («Åbn listen»), en klar hemmeligheds-forklaring («Mette kan ikke se, hvad du reserverer») og en ærlig fejlside («Invitationen findes ikke længere»).
- **Justér:**
  - «Du skal have en gratis privat konto» står før knappen. Vend det om: knap først, derefter «Det tager et minut – gratis».
  - Header-pillen «Privat» er grå her og orange i appen. Ensret.
  - Reklamekortet «Mette bruger Dialogbot …» er fint, men skal under folden.

### 1.11 Ønskeliste: ejer og gæst
Se 1.5. Gæsten har hele appskallen (Min dag med installér-kort, Peter-chat, Apps, Folk og «Dit råderum: Start 14 dage gratis»).
- **Brief:** «kan åbne listen, men ikke meget andet».
- **Ændring:** En gæst uden plan får en **gæsteskal**: kun «Delt med mig» plus én blød «Få din egen» nederst. Ingen tab-bar med fem faner.

### 1.12 Kalender (`/privat/kalender` → app-siden Kalender)
- Fire orange knapper (se 1.8).
- «1× – eller bare din iPhone-kalender» er en chip, der begynder med tankestreg.
- **Ændring:** Én valgt vej: «Hvilken kalender bruger du?» med tre store valg (Google · Outlook · iPhone/andet). Valget giver én orange knap.
- **Ærlighed:** «Forbind» skal give «ikke sat op endnu», når OAuth-nøglerne mangler (integrations-qa ejer testen).

### 1.13 Konto (`components/privat/account.tsx`)
- **Ti kort:** Abonnement, Ekstra opkald, Bevægelser, Mobilnummer, Sprog, Hent appen, Notifikationer, By, Assistentens navn, Inviter venner og «14 apps slået til».
  - Titlen «Konto og credits» introducerer et tredje begreb (credits) ved siden af «opkald» og «plan».
  - «Ingen plan» står tre gange på samme kort (chip, titel og brødtekst) plus «Uden plan» i headeren.
  - Emailen efterfølges af «adskilt fra virksomhedskonti» (jargon).
- **Ændring:** Øverst kun **Din plan** (navn, dage tilbage, opkald brugt, én knap «Skift plan»). Derefter tre korte grupper som rækker med chevron, ikke kort:
  - **Dig** (mobil, sprog, by, assistentens navn)
  - **Appen** (hent, notifikationer)
  - **Ekstra** (køb opkald, inviter venner, bevægelser)
- **Plan-vælger:** Tre fulde kort. Rækkefølgen skal være **Plus (Anbefalet) først** og forvalgt. I dag står Basis øverst, og det første tryk vælger Basis.
- **Mockup:** `mockups/konto-plan.html`.

### 1.14 Offline-siden (`components/offline-page.tsx`)
- **Godt:** Én primær («Prøv igen»), en ærlig tekst og en sekundær «Vis det sidste, jeg så».
- **Fejl:** Andre faner end appen (**F-UX-07**). «PRIVAT»-pillen er orange her og grå på invitationssiden.

### 1.15 Gennemgående
- **Header (390 px):** Plan-chippen dækker PRIVAT-mærket og klipper ordmærket (**F-UX-05**). Chippen bør være en prik plus «14 dage» eller kun en avatar-ring.
- **Navngivning:** Fanen hedder «Apps», siden hedder «Mine apps», segmentet hedder «Butikken», offline siger «Butikken», og Konto siger «14 apps slået til». Briefen bruger «Butik». **Beslutning (forslag):** Fanen hedder «Apps»; inde i den er der «Mine» og «Butik».
- **Gul:** Bruges i dag på trin-tal, «Trin 1»-piller (×11), app-kort (×14), avatarer, prøveperiode-pille og bjælker. Reglen er «gul = her er du». Højst ét gult element pr. skærm ud over trin-tal.
- **Blok-skygge:** Sidder på 2-3 kort pr. skærm. Reglen er én pr. skærm: det kort, der bærer den ene handling.
- **Mål:** Alle knapper og felter er ≥ 44 px bortset fra to `<select>` på 40 px (Fødselsdage → Påmindelse og Konto → Sprog). «Spring til indholdet» er korrekt skjult.
- **Tilstande:** Tomme tilstande findes (Opgaver, Folk, Garanti, Kalender). Indlæsning er en `role=status`-tekst. Fejl ved 409 `needs_plan` bruger en ufærdig tekst (F-UX-01).

---

## 2. Rangeret liste (impact × indsats)

Impact: H = flytter aktivering eller tillid, M = forståelse, L = kosmetik. Indsats: S < ½ dag, M 1-2 dage, L > 2 dage.
Fase 2-ejer: **UX** = ui-ux-engineer (layout/komponenter/tekst), **FIX** = fix-engineer (logik/API). Koordinér med fix-engineer (agent-id `a87a034415f1beee5`) før filer i `web/src/app/privat` eller `web/src/components/privat` røres.

| # | Skærm | Ændring | Tag | Fil | Impact | Indsats | Metrik | Ejer |
|---|---|---|---|---|---|---|---|---|
| 1 | Konto/checkout | Ret trial-teksten til den rigtige plan; 409-tekst i trial = «Skift til Plus» | ADJUST | `account.tsx:138`, `i18n/*/privat.json plan.trialLine`, `addons.py` needs_plan-besked | H | S | færre support-/opsigelser; app-aktivering | FIX (F-UX-01) |
| 2 | Min dag | Ny rækkefølge: Peter-composer → «Din tur» (kun hvis noget venter) → «I dag» (≤ 3 rækker) → én linje «Se alle opgaver». Fjern AppsStrip, filterchips og RoomCard fra Dag | ADJUST | `day.tsx` DayPage, TasksSection, RoomCard | H | M | første opgave inden 60 s; ord 326 → < 120 | UX |
| 3 | Min dag | Installér-kortet først efter første gemte opgave, som en tynd linje under «I dag», og aldrig for gæster uden plan | ADJUST | `day.tsx` FirstOpenInstall, `install-app.tsx` | H | S | install rate (pr. aktiv bruger, ikke pr. besøg) | UX |
| 4 | Checkout-retur | success_url → `/privat/dag?velkommen=plan` med én gul bjælke; ikke Konto | ADJUST | `subscriptions.py` success_url, `day.tsx` WelcomeBanner | H | S | første opgave efter trial-start | FIX + UX |
| 5 | Ønskeliste (gæst) | Gæstevisning uden «Næste skridt», historik og «Tal om opgaven»; gæsteskal uden fem faner | ADJUST/NEW | `tasks.tsx` TaskDetail, `shell.tsx` (guest mode) | H | M | reservationer pr. åbnet invitation; gæst → trial | FIX (F-UX-02) + UX |
| 6 | Ønskeliste (ejer) | «Del» som den ene orange knap øverst; kompakte ønskerækker; ingen 200 px pladsholderbilleder; skjul «Delt med –» | ADJUST | `wishes.tsx` WishList/WishCard/WishImage, `tasks.tsx` | H | M | delinger pr. ønskeliste | UX |
| 7 | App i brug | Når der er data: dine ting først; opsætning som én gul linje; én orange knap; «Om appen»-fold for «Den får lov til» + «Slå fra» | ADJUST | `apps.tsx` AppPage/SetupCard | H | M | aktive apps pr. bruger (7 dage) | UX |
| 8 | Apps | Opsætnings-trin regnes som klaret, når appen har data | ADJUST | `apps.tsx:34`, `addons.py` setup | M | M | færre gule piller; app-aktivering | FIX (F-UX-04) |
| 9 | Butikken | Vis kun apps, der *ikke* er slået til; samme ikonflise for alle (orange flise, hvidt ikon) | ADJUST | `apps.tsx` Store, `icons.tsx` | M | S | tryk på app → «Slå til» | UX |
| 10 | App-detalje (butik) | «Du skal bruge»-boks før «Sådan virker den»; «Hvad den gør» ≤ 25 ord; ikon i stedet for «‖» | ADJUST | `apps.tsx` (StorePage ~300-345), `addons.py` description | M | S | Slå til-rate pr. app-visning | UX |
| 11 | Konto | Plan øverst, resten som tre grupper af rækker; titel «Konto»; Plus forvalgt og først i plan-vælgeren | ADJUST | `account.tsx` AccountPane, PlanPicker | M | M | trial → Plus-andel; ord 250 → < 120 | UX |
| 12 | Header | Plan-chip som prik + «14 d»; PRIVAT-mærke altid synligt; landing-header på én række | ADJUST | `shell.tsx` Header, `site-chrome.tsx` | M | S | – (brand: Privat genkendes) | UX (F-UX-05) |
| 13 | Samtale | Kompakte resultatkort i chatten (titel, antal, «Åbn» og «Del») | ADJUST | `chat.tsx`, `cards.tsx` ListCard | M | S | – (chat-scroll; INP) | UX |
| 14 | Folk / Del | Delingsark: valg af modtager (grupper + link) → SMS-forhåndsvisning → «Send»; ønskeliste-gæst = «kan reservere»; ingen «Fælles liste»-skift for ønskelister | ADJUST | `sheets.tsx` ShareSheet, `people.tsx` | M | M | invitationer sendt pr. delt liste | UX + FIX (F-UX-03) |
| 15 | Landing | Én primær + én sekundær knap i hero; «Download app» flyttes ned | ADJUST | `app/privat/page.tsx`, `public.tsx` | M | S | CTA-klik → trial-start | UX |
| 16 | Kalender | «Hvilken kalender bruger du?» (3 valg) → én orange knap | ADJUST | `calendar.tsx`, `apps.tsx` | M | S | forbundne kalendere | UX |
| 17 | Tema | Neutral ønskeliste-tema og hjemmeskærm-guide i Privat-orange | ADJUST | `lib/privat/wish-themes.json`, `push.tsx` | L | S | – | UX (F-UX-06) |
| 18 | Offline | Samme faner som appen | ADJUST | `components/offline-page.tsx:56` | L | S | – | UX (F-UX-07) |
| 19 | Opgaver | Drop status-pille i grupperede lister; én tidslinje («I morgen 17.00») | ADJUST | `tasks.tsx`, `day.tsx` DayPill | L | S | – | UX |
| 20 | Desktop-nav | Samme 5 punkter som mobilfanerne (inkl. Folk) | ADJUST | `shell.tsx` nav | L | S | – | UX |
| 21 | Småfejl | Konto-statistik-etiketter, `<select>` 44 px, app-bånd på desktop | ADJUST | `account.tsx` InviteFriends, `apps.tsx`, `day.tsx` | L | S | – | UX (F-UX-08) |

---

## 3. Privat design-principper (10 regler til testere og fix-engineer)

1. **Én orange knap pr. skærm.** Alt andet er en blæk-kontur eller et link. Test: tæl elementer med `bg-accent` over folden. Mere end 1 er en fejl.
2. **Peter først.** På Min dag er composeren det første interaktive element. På mobil sidder den i tommelfingerzonen (bunden).
3. **Højst 120 ord over folden** (390 × 844). Forklaringer ligger bag «Om appen»- eller «Sådan virker det»-folde.
4. **Gul betyder «her er du».** Kun trin-tal og ét «det er her, du er»-element pr. skærm. Aldrig som kortfyld i serie.
5. **Vis dine ting før opsætning.** Har en app data, står dataene øverst. Opsætningen er en tynd linje, ikke et kort.
6. **«Du skal bruge» før «Gør sådan».** Det gælder hver app-side og hvert trin, der kræver noget fra brugeren (kort, nummer, kalender).
7. **En gæst ser kun det, der er delt med ham.** Ingen ejer-metadata, ingen fem faner, ingen betalingsopfordring før han selv har gjort noget.
8. **Privat er orange, altid.** Ingen #2456F6 eller #EEF4FB i Privat-flader. Logo og PRIVAT-mærke må aldrig dækkes eller klippes. Én blok-skygge pr. skærm.
9. **Ét ord pr. ting.** «Apps» (fanen) med «Mine» og «Butik» inde i den. «Opkald» (ikke «credits») i brugertekst. «Plan» (ikke «abonnement» og «råderum» på skift).
10. **Ærlige tilstande.** Tom = én sætning plus ét eksempel at sige til Peter. «Kommer snart» = «Giv mig besked», aldrig «Slå til». Ingen grøn status for noget, der ikke er forbundet. Mål ≥ 44 px, og tekst ≥ 4,5:1 (`#C4461A` på papir er 4,81).

---

## 4. Mockups (før → efter)

| Fil | Skærm | Kerne |
|---|---|---|
| `mockups/dag.html` | Min dag | 6 sektioner → 3. Peter i bunden, «Din tur» kun når noget venter |
| `mockups/butik-app.html` | Butik → app-detalje og app i brug | «Du skal bruge», 3 trin, én «Slå til»; app i brug med dine ting først |
| `mockups/konto-plan.html` | Konto og plan-vælger | Plan øverst, rækker i stedet for 10 kort; Plus forvalgt |
| `mockups/folk-inviter.html` | Folk og Del | Én «Del»-strøm: modtager → SMS-forhåndsvisning → Send; gæstevisning af ønskeliste |

Alle mockups bruger de rigtige tokens (`#14213D`, `#C4461A`, `#FFFBF5`, `#FFF4E6`, `#FFCF3F`), Outfit/Inter med systemfald-back og 390 px-telefonrammer side om side.

---

## 5. PWA-noter (kort; X23 ejes af i18n-a11y-qa)

- **Installér-øjeblik:** Ikke ved første besøg. Det kommer efter første gemte opgave eller efter første «Ja, ring» (`day.tsx` FirstOpenInstall). På iPhone bruges HomeScreenGuide med orange ikon. «Åbn siden på din telefon» må kun vises på desktop-UA. I testen var UA desktop Chrome ved 390 px, så teksten var teknisk korrekt. Den skal verificeres på en rigtig telefon.
- **Offline:** Fanerne skal svare til appens (F-UX-07).
- **Push:** «Notifikationer er blokeret i browseren» vises på Konto *og* på hver påmindelse i chatten. Vis det ét sted (Konto → Appen).

## 6. Observationer uden fund (kan skyldes `AI_PROVIDER=fake`)

- «Lav en indkøbsliste: mælk, rugbrød, æg» gav en **tom** indkøbsliste, mens «… med te, kaffe og en racercykel» gav 3 ønsker. Kolon-formen ser ikke ud til at blive parset.
- «Mind mig om at betale vand-regningen d. 28» svarede «Du har ikke gemt nogen regninger endnu» i stedet for at lave en påmindelse.
- Begge bør køres igen af voice-/e2e-privat med rigtig model.
- Serverens ur stod på 11. november, mens browseren viste 10. november. Det gav «i morgen kl. 17.00 · Torsdag kl. 17.00». Det er en miljøsag, men det viser, at relative («i morgen») og absolutte datoer regnes forskellige steder.
