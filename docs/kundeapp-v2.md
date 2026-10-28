# Kundeapp og opsætning v2 — «Byggevejledningen» i appen

Spec for at bringe kundens backend (`/app/*`) og opsætningen (`/onboarding/*`, `/app/setup`) på v2-designet.
Gælder sammen med `docs/brand.md` (princip, farver, typografi) og boards i `design-reference/byggevejledning/`.
Operatør-siderne (`/app/operator/*`) er IKKE omfattet – de må gerne vente.

Designcanvas (samme boards, til at klikke rundt i): «Dialogbot — Kundeapp og opsætning».

## 1. Hvad der er galt i dag (kort)

- 38 kundesider, ~25 af dem 85 %+ i gamle Material-klasser (`text-on-surface-variant`, `bg-surface-container-lowest`, `font-body-sm` …). Kun `/app/overview` er v2.
- Samme ting bor flere steder: telefoni på 5 sider (overview, settings/telephony, reception, voices, setup), script/test på 2 (reception + knowledge r05/r06), fakturering på 3 (billing, settings/agreement, lead-panel), opgaver 2 indgange.
- Indstillinger uden for Indstillinger: booking-regler på /bookings, rapportindstillinger på /reports, stemme på /voices.
- Onboarding spørger om produkt og vejledning to gange (workspace + goals, business + goals); `/onboarding/languages` ender på `/app/knowledge`, ikke på trin 3; `/app/setup` («Personlig plan», 5 poser, 621 linjer) gentager onboarding og linker til `/app/not-yet`.
- Menuen: 3 faner + «Mere» med 12 punkter + kontomenu + 8 settings-faner. Mobil: hamburger, ingen bundfaner.

## 2. Princippet (fra brand.md, anvendt på appen)

1. **Fire sider.** I dag · Det ved den · Opkald · Ugen. Ingen «Mere»-menu. Alt andet nås fra I dag (aftaler, kampagner), fra profil-avataren (Konto) eller via «Alle indstillinger» (reservedelslisten).
2. **Assistenten «Ændr noget» ligger overalt** (højre kolonne på desktop, ark i fuld skærm på mobil). Tunge funktioner ligger bag den – aldrig i menuer. Den viser altid *før → efter* og spørger «Godkend?», før noget gælder.
3. **Opsætning = tre trin**, ikke fem poser: 1 Virksomhed · 2 Kalender & systemer · 3 Test & tænd. Derefter lander man på I dag.
4. **Hver skærm er ét trin**: nummer, overskrift, «Du skal bruge», fladt billede/indhold, kort tekst. Én primær knap pr. skærm.
5. **Kun v2-tokens** i berørt kode: `bg-accent`, `text-ink`, `text-ink-soft`, `text-muted`, `bg-panel`, `border-ink`, `bg-highlight`, `shadow-block`, `font-display`. Ingen `surface*`, `primary*`, `on-*`, `font-body-*`, `space-*` i filer, der røres.

## 3. Ny informationsarkitektur og route-map

| Ny route | Board | Erstatter (redirect 308) |
|---|---|---|
| `/opsaetning/1` Virksomhed | `Trin1.dc.html` | `/onboarding/workspace`, `/onboarding/business`, `/onboarding/goals`, `/onboarding/languages`, `/app/settings/business` |
| `/opsaetning/2` Kalender & systemer | `Onboarding.dc.html` | `/app/settings/integrationer` (opsætningsdelen), booking-opsætning fra `/app/bookings` |
| `/opsaetning/3` Test & tænd | `Taend.dc.html` | `/app/settings/telephony` (wizard), `/app/voices` (valg), `/app/settings/webchat` (kodestump), `/app/not-yet?area=Prøveopkald` |
| `/app` = I dag | `Dashboard.dc.html` | `/app/overview`, `/app/setup` (når opsætningen er færdig) |
| `/app/viden` Det ved den | `Viden.dc.html` | `/app/knowledge` (alle tabs), `/app/reception` (manuskript + test) |
| `/app/opkald` + `/app/opkald/[id]` | `Opkald.dc.html` | `/app/inbox`, `/app/inbox/[id]`, `/app/leads`, `/app/leads/[id]`, `/app/tasks`, `/app/notifications` |
| `/app/ugen` | `Ugen.dc.html` | `/app/reports` (+ rapportindstillinger) |
| `/app/aftaler` | `Aftaler.dc.html` | `/app/bookings` |
| `/app/kampagner` + `/app/kampagner/[id]` | `Kampagner.dc.html` | `/app/campaigns`, `/app/campaigns/[id]` |
| `/app/konto` | `Konto.dc.html` | `/app/settings/team`, `/app/settings/profile`, `/app/billing`, `/app/settings/agreement`, `/app/settings/activity` (link) |
| `/app/indstillinger` Alle indstillinger | `Avanceret.dc.html` | `/app/settings/*` som oversigt; detaljer åbner som ark |
| `/app/hjaelp` | (ingen board – kort side m. 5 spørgsmål + «Spørg assistenten») | `/app/help` |
| `Mobil.dc.html` | app-skallen på telefon | – |

Gamle routes bliver liggende som redirects i mindst én release (`next.config.ts` redirects), så e-mails, PWA `start_url` og invitationer ikke knækker. `/app/not-yet` slettes, når intet peger på den.

`/app` sender til `/opsaetning/1`, hvis arbejdsrummet ikke har gennemført trin 3 (`setup/plan` siger, om telefonen er forbundet og aktiveret); ellers til I dag.

## 4. App-skallen (`shell.tsx`, `shell.client.tsx`)

**Desktop (≥ 640 px):** hvid header, 2 px blæk-kant. Venstre: mærke + «Dialogbot» (→ I dag) og arbejdsrummets navn (dropdown kun hvis > 1 arbejdsrum). Midt/højre: pille-nav med de fire faner (valgt = blæk-fyld). Højre: gul avatar med initial → `/app/konto`. Ingen klokke (notifikationer er «Til dig» på I dag og Opkald), ingen AI-status-pille (status står på I dag), ingen «Mere».

**Mobil (< 640 px):** header med mærke + avatar. **Bundfaner** med de fire sider (ikon + etiket, valgt = gul pille bag ikonet). Flydende knap «✎ Ændr noget» nederst til højre åbner assistenten som ark i fuld skærm (samme mønster som `ChatWidget` i PR #71: `fixed inset-0`, luk-kryds, siden bagved låses). Intet andet skjules bag en menu.

**Operatør:** `is_platform_operator` får ét ekstra punkt i Konto-siden («Operatør») – ikke i hovednavigationen.

**Under opsætningen** (`/opsaetning/*`): samme header, men nav'en er erstattet af stepperen (1 Virksomhed → 2 Kalender & systemer → 3 Test & tænd). Ingen bundfaner på mobil; «Videre»-knappen er sticky i bunden.

## 5. Assistenten «Ændr noget» (`components/assistant.tsx`)

Én komponent, brugt som højre kolonne (desktop, `position: sticky`) og som ark (mobil). Samme komponent på alle fire sider, i Alle indstillinger og i opsætningen (dér hedder den «Jeg hjælper med trin N»).

Indhold: hilsen + 3 kontekst-chips (I dag: «Ret åbningstider», «Tilføj en pris», «Vis ugens tal»; Det ved den: «Læs min prisliste ind», «Test mig som kunde» …), beskedlog, inputfelt. Når den foreslår en ændring, viser den et **ændringskort**: eyebrow «Ændring · før → efter», to tags (før = blæk-kontur, efter = gul), knapperne «Godkend» (primær) og «Nej, lad være». Intet gælder før Godkend. Godkendte ændringer logges (revisorlog, `settings/activity`).

Backend: nyt modul `app/modules/assistant/` med
- `POST /workspaces/{id}/assistant/changes` `{text, context}` → `{proposal_id, summary, before, after, kind}` – LLM’en oversætter fri tekst til én af de kendte ændringstyper (åbningstider, pris/ydelse, Q&A, forbudt emne, bookingregel, rapportmodtager/-tid, SMS-afsender, viderestilling, stemme) og returnerer før/efter **uden at gemme**.
- `POST /workspaces/{id}/assistant/changes/{proposal_id}/apply` → udfører via de eksisterende service-funktioner (knowledge drafts + approve, bookings/settings, reports/settings, telephony …) og skriver audit.
- Kan den ikke forstå det, svarer den med et spørgsmål eller et link til det rigtige felt i Alle indstillinger – aldrig med «fejl».
- Fase 1 kan bruge chips som deep-links og genbruge `assistant/preview` til «Test mig som kunde»; den generiske propose/apply er fase 3.

## 6. Skærm for skærm

Alle felter/endpoints herunder findes allerede, medmindre andet er nævnt. Boards viser indhold og rækkefølge; teksterne i boards er den copy, der skal bruges (eksempeldata som «Nørgaard Tømrer» er selvfølgelig data).

### 6.1 Opsætning trin 1 – Virksomhed (`Trin1.dc.html`)
- Første gang (intet arbejdsrum): siden opretter arbejdsrummet ved «Videre» (`POST /workspaces`), navn = feltet «Navn». Ambassadørkode kommer fra cookie – ikke et felt.
- A «Hent det fra hjemmesiden»: URL + «Hent» → `knowledge/import` + `knowledge/imports/latest`; fundne fakta som tags med ✓/? og «Godkend alle» / «Ret det gule» (→ `knowledge/versions/{id}/approve`). CVR-opslag (`cvr/{n}`) kører automatisk, når et CVR findes.
- B «Om jer»: navn, telefon kunderne ringer til, hvad I laver (én sætning), åbningstider, hvor I kører → `profile` (+ `categories` afledes af «hvad I laver»; ingen kategori-søgefelt).
- C «Hvad skal den gøre for jer?»: 4 afkrydsnings-kort (tage telefonen, booke aftaler, svare på hjemmesiden, ringe kunder op) → `goals` (product_intent + channels). Sprog: chips «Dansk» (+ Engelsk, + Tysk) → `languages.allowed`; UI- og rapportsprog er altid dansk (felterne fjernes fra UI, backend beholder default).
- Guided/self-managed fjernes fra UI (default guided).
- Assistent til højre: «Jeg hjælper med trin 1».
- «Videre til trin 2» gemmer alt (optimistisk, løbende autosave).

### 6.2 Opsætning trin 2 – Kalender & systemer (`Onboarding.dc.html`)
- Valg: Google Kalender / Microsoft 365 / andet system (fritekst til assistenten) → `integrations/{key}/connect` (OAuth-vindue), status «Forbundet · synk for 2 min siden».
- «Det skriver Dialogbot i kalenderen»: varighed, pause, hvornår der må bookes, max pr. dag, SMS-bekræftelse → `bookings/settings` med fornuftige defaults (45 min / 15 min / man–fre 08–15 / aldrig samme dag / max 3).
- Kan springes over («Jeg har ingen kalender – tag besked i stedet»). Trin 2 vises kun, hvis «Booke aftaler» er valgt i trin 1; ellers går man direkte til trin 3 (stepperen viser stadig 3 trin, trin 2 som «sprunget over»).

### 6.3 Opsætning trin 3 – Test & tænd (`Taend.dc.html`)
- A Stemme: 3–4 stemmer med «Hør» (`voices` + `voices/settings`), udtaletræning af firmanavnet (`voices` fonetik).
- B Telefon: «Behold jeres nummer» → viderestillingskoder (altid / kun når I ikke svarer), status på nummer (`telephony`, `telephony/business-number`, `verify`, `connect`). Dokument-upload kun hvis `telephony` kræver det (vises som ét trin «Send dokumentation»).
- Prøveopkald: «Ring til mig nu» → `telephony/tests` (erstatter `/app/not-yet?area=Prøveopkald`).
- C Webchat: til/fra + kodestump til at kopiere (`webchat`); tilladte domæner udfyldes fra hjemmesiden i trin 1.
- TÆND: `telephony/activate`. Derefter redirect til I dag med gul «Dialogbot er tændt»-stempel (`stamp-in`).

### 6.4 I dag (`Dashboard.dc.html`) – findes som `/app/overview`
- Behold den nuværende side; flyt til `/app`. Ændringer: ChangePanel erstattes af den rigtige assistent (afsnit 5); «Seneste opkald» læser fra `conversations` (samme kilde som Opkald), ikke `telephony/calls`; «Til dig» = leads uden afgørelse + åbne opgaver + ubesvarede webchat-henvendelser (én liste, `leads?status=open` + `tasks?status=open`).
- To kort nederst: «Aftaler» (næste 3, link til `/app/aftaler`) og «Kampagner» (kun hvis «ringe kunder op» er valgt).

### 6.5 Det ved den (`Viden.dc.html`) – findes halvt som `/app/knowledge`
- Fire nummererede bokse: 1 Om jer (redigér inline – ikke link til onboarding), 2 Det I sælger (ydelser med «Sælger / Kun hvis spurgt»-toggle, «Tilføj en ydelse» = 3 felter + «Gem – og vis mig, hvordan den siger det» → `assistant/preview`), 3 Spørgsmål kunderne stiller (godkendt / foreslået fra ugens opkald → `knowledge/review-queue`, Godkend/Ret/Afvis), 4 Det må den ikke (regler).
- Sub-tabs (k01/k03/k04/k05/r05/r06) fjernes. Hjemmeside-import og tilbud/rabatter flytter ind i assistenten («Læs min prisliste ind», «Hent fra hjemmesiden») og i boks 2. Manuskript (hilsen, spørgsmål, overlevering) flytter til Alle indstillinger → Telefon → Hilsen (ark). «Test den – spørg som en kunde» er assistentens anden tilstand.
- AI-forbrug (`ai/usage`) vises ikke for kunder.

### 6.6 Opkald og beskeder (`Opkald.dc.html`) – ny, erstatter inbox/leads/tasks/notifications
- Liste grupperet pr. dag: tid · navn/nummer · ét-linjes resumé · udfald-tag (Aftale booket / Til dig / Klaret / Webchat) · «▶ Hør». Kilde: `conversations` (alle kanaler) beriget med `conversations/{id}/lead`, booking-udfald og opgave-status (backend: nyt felt `outcome` på conversation-listen, så listen kan laves i ét kald).
- Filterchips: Alle · Til dig (tæller) · Aftaler · Klaret af Dialogbot · Webchat · dato. Søgefelt.
- Detalje (højre kolonne / ark på mobil): header med tid, varighed, udfald; lydafspiller (`telephony/calls/{id}/recording` – findes? ellers skjul knappen); udskrift som bobler; «Det gjorde Dialogbot» (handlinger); knapper «Ring tilbage» (`tel:`), «Lav en aftale» (→ aftaler med navn/telefon udfyldt), «Marker som klaret» (lukker lead/opgave), «Svar i chatten» for webchat (`conversations/{id}/reply`, human/AI-mode).
- Leads’ tre status-dimensioner (kvalifikation, pipeline, fakturering) vises ikke her; de bor i Konto → faktura-tvister / operatør.

### 6.7 Ugen (`Ugen.dc.html`) – erstatter reports
- Ugevælger. Fire tal: opkald besvaret (+ mistet), aftaler booket (+ delta), beskeder til dig, svartid. Søjler pr. dag (blå = besvaret, gul = besked til dig) – flade divs, ingen chart-lib.
- «Det spurgte kunderne om»: emne · gange · kunne svare (Ja / Nej · tog besked / Må den ikke) · «Tilføj svar →» (deep-link til Det ved den med emnet udfyldt). Backend: `reports/topics?week=` (nyt; aggregér fra conversation-resuméer).
- Højre: Dagsrapport (modtager, klokkeslæt, ugemail) – ændres via chips/assistenten → `reports/settings`. «Det kostede ugen» (kampagneopkald × 4 kr.) → `billing/account`.

### 6.8 Aftaler (`Aftaler.dc.html`) – erstatter bookings
- Ugestrimmel man–fre med aftalekort (i dag = gul); lukkedage som stiplet felt. Klik på aftale → lille ark: flyt/aflys (`bookings/{id}`, `/cancel`), kunden får SMS.
- «Book for en kunde»: navn, telefon, hvornår (fritekst «først ledige» → `bookings/slots`) → `bookings` + SMS.
- Højre: kalenderstatus (`bookings/calendar/sync`), «Sådan booker den» (læse-visning af `bookings/settings` + chips til assistenten). Bookingtyper redigeres i Alle indstillinger → Booking.

### 6.9 Kampagner (`Kampagner.dc.html`) – erstatter campaigns
- Ny kampagne som tre nummererede trin på én side: 1 Hvem (upload CSV/XLSX → `campaigns/{id}/contacts`; viser antal og hvor mange der springes over pga. `do-not-call`), 2 Hvad skal den sige (manuskript + «Hør det med jeres stemme» + chips via `script-suggestions`), 3 Hvornår og hvad gør den ved svar (tidsvindue, forsøg, ja → book, nej → ring-ikke).
- Gult godkendelseskort: antal opkald · højst X kr. ekskl. moms (antal × 4) · «Godkend og start» (`campaigns/{id}/start`) · «Ring til mig først som test».
- Højre: tidligere kampagner med resultat (ringet / svarede / aftaler / kr.), «Ring ikke»-listen (tilføj nummer).
- Prislinje altid: «4 kr. pr. opkald ekskl. moms». Siden vises kun, hvis «ringe kunder op» er valgt i trin 1 (ellers et kort på I dag: «Vil I også ringe ud? Sig det til assistenten»).

### 6.10 Konto (`Konto.dc.html`) – erstatter team/profile/billing/agreement
- 1 Hvem må se og ændre: tabel (navn, e-mail, rolle som dropdown «Ejer / Kan ændre / Kan se», fjern), invitationer, invitér-felt → `members`, `invitations`. Rollerne mappes: owner=Ejer, admin+staff=Kan ændre, reader=Kan se (backend uændret).
- 2 Abonnement: fast abonnement 2.495 kr./md. ekskl. moms · kampagneopkald 4 kr. · betaling (kort •••• / EAN) → `agreement`, `billing/account`, `billing/card/checkout`. Første gang ejeren ser siden uden bekræftet aftale, står boksen gul med «Bekræft abonnement» (= nuværende settings/agreement).
- 3 Fakturaer: måned · abonnement · kampagner · i alt · PDF/Åben → `billing/invoices`.
- Højre: profil (navn, e-mail, skift adgangskode, log ud, sessioner → `/auth/sessions`), andre arbejdsrum (+ «Byg en Dialogbot til en anden virksomhed» → `/opsaetning/1`), data og samtykke (link til log).
- Ambassadør-/henvisningskode: ét felt under Abonnement («Har du en ambassadørkode?»), ikke tre steder.

### 6.11 Alle indstillinger (`Avanceret.dc.html`) – erstatter settings-fanerne
- Søgefelt, status-legende (Klar · På vej · Ikke sat op), «Vis teknik»-toggle (API-nøgle, webhooks, log/eksport skjult som standard).
- 8 kapitler som brikker (Telefon, Viden, Kanaler, Booking, Kampagner, Systemer, Team og konto, Teknik) – værdier læses fra de respektive endpoints og vises som én linje pr. brik.
- «Ændr» på en brik åbner **enten** assistenten med brikken som kontekst (simple værdier) **eller** et ark med den eksisterende formular (telefoni-wizard, webchat-domæner, integrationer, team) – arket er den gamle side renset til v2-tokens, uden egen h1 og tab-bar.
- Historik → `settings/activity` som ark.

### 6.12 Mobil (`Mobil.dc.html`)
- Alle fire sider ved 390 px: én kolonne, kort fylder bredden, tal-fliser 3 i rækken, assistent som ark, detaljer (opkald, aftale) som ark nedefra. Bundfaner som beskrevet i afsnit 4. Ingen vandrette scroll-tabeller uden `overflow-x: auto`-boks.

## 7. Rækkefølge (én PR pr. fase, hver fase grøn på `npm run e2e`)

1. **Skal + routes.** Ny shell (4 faner, avatar, bundfaner, assistent-pladsholder med chips), `/app` → I dag, nye routes som tynde wrappers om de nuværende sider, redirects for alle gamle routes, `/app/not-yet` væk. `e2e/journeys.spec.ts` opdateres til nye routes/labels.
2. **Opsætning 1–3.** `/opsaetning/1..3` bygget efter boards; `/onboarding/*` og `/app/setup` → redirects. Signup/verify/invite lander i trin 1. `setup/plan` bruges kun til at afgøre «færdig eller ej».
3. **Assistenten.** `components/assistant.tsx` + backend `assistant/changes` (propose/apply) for: åbningstider, ydelse/pris, Q&A, forbudt emne, bookingregler, rapportindstillinger. Chips → deep-links, hvor propose ikke dækker endnu.
4. **Det ved den + Opkald + Ugen.** Efter boards; knowledge-tabs, inbox, leads, tasks, notifications, reports afvikles (redirects beholdes).
5. **Aftaler + Kampagner + Konto + Alle indstillinger.** Gamle settings-sider bliver ark; billing/agreement/team/profile samles i Konto.
6. **Oprydning.** Fjern Material-aliasser fra `globals.css`, når `grep -r "surface\|on-primary\|font-body-" web/src/app/app` er tom. Slet døde sider og `ROUTE`-remap i setup.

## 8. Regler, der ikke må brydes

- Priser kun som: «abonnement fra 2.495 kr./md.» og «4 kr. pr. udgående kampagneopkald», altid «ekskl. moms». Ingen påstande om ISO, hosting, SLA eller «gratis» (undtagen «gratis opsætning»).
- Ingen gradienter, bløde skygger eller emoji. Eneste skygge: `shadow-block` (8px 8px 0 blæk), én pr. sektion.
- Rigtige `<a>`/`<button>`/`<label>`; knapper ≥ 44 px; kontrast 4,5:1; alt virker ved 390 px.
- Intet gemmes uden «Godkend», når det går gennem assistenten. Direkte formularer (fx trin 1) autosaver, men viser «Gemt».
- Ingen nye npm-pakker til layout/charts.
- Backend-ændringer er additive (nye endpoints/felter); eksisterende endpoints og operatør-sider rører vi ikke.
