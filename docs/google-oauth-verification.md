# Google OAuth-verificering – Kalender (Privat og erhverv)

Dialogbot beder om adgangen `https://www.googleapis.com/auth/calendar.events` (følsom). Indtil Google har verificeret appen,
kan højst **100 brugere** forbinde, de ser advarslen «Google har ikke bekræftet denne app», og i «Testing» udløber adgangen efter
7 dage. Verificeringen tager typisk 1–4 uger efter indsendelse. iPhone, Outlook og kalenderlinket afhænger ikke af den.

Ansøgningen kan kun sendes af ejeren af Google Cloud-projektet (Google Cloud Console). Claude har ikke adgang dertil; alt nedenfor
er forberedt, så det kun skal indsættes.

## 0. Forudsætninger (skal være på plads før indsendelse)

| # | Hvad | Status |
|---|---|---|
| 1 | `dialogbot.dk` er verificeret i Google Search Console under den samme Google-konto, som ejer Cloud-projektet | tjek selv |
| 2 | Privatlivspolitikken (`https://dialogbot.dk/privatliv`) nævner Dialogbot Privat, Google-kalenderdata og Limited Use (afsnittet i §4, på 8 sprog) | lagt på siden 5/11 2026 efter ejerens ja; gerne set af en advokat |
| 3 | Forsiden `https://dialogbot.dk` beskriver produktet og linker til privatlivspolitikken | ok |
| 4 | Login-forløbet virker i produktion fra Privat (Apps → Kalender → Forbind Google) | efter deploy af checkpoint 32 |
| 5 | Redirect-URI i OAuth-klienten: `https://api.dialogbot.dk/api/v1/integrations/oauth/google_calendar/callback` | tjek, at den står der præcis sådan |

## 1. Google Cloud Console → Google Auth Platform → Branding

| Felt | Værdi |
|---|---|
| App name | Dialogbot |
| User support email | den support-adresse, I bruger (fx kontakt@dialogbot.dk) |
| App logo | Dialogbot-logoet, 120×120 px PNG (kræver også verificering af logoet) |
| Application home page | `https://dialogbot.dk` |
| Application privacy policy link | `https://dialogbot.dk/privatliv` |
| Application terms of service link | `https://dialogbot.dk/vilkaar` |
| Authorized domains | `dialogbot.dk` |
| Developer contact information | jeres e-mail |

## 2. Data Access → scopes

Tilføj præcis disse (ikke flere):

- `openid`, `.../auth/userinfo.email` (ikke-følsomme)
- `.../auth/calendar.events` (følsom)
- `.../auth/calendar.freebusy` (følsom – bruges kun af erhvervsdelen til at se optaget tid; lad den stå, hvis erhvervskunder bruger Google Kalender)

**Begrundelse til `calendar.events`** (feltet «How will the scopes be used?», på engelsk):

> Dialogbot is a personal and business assistant. When a user has approved an appointment – a time a business confirmed on a phone
> call the user approved, a booking the user confirmed, or a time the user told the assistant – Dialogbot creates that one event in
> the user's own calendar, and updates or deletes it if the appointment is moved or removed. Dialogbot only creates, updates and
> deletes the events it created itself; it never reads, lists or changes the user's other events. We considered
> `calendar.app.created`, but it would put the appointments in a separate secondary calendar instead of the user's own calendar,
> which defeats the purpose of the feature.

**Begrundelse til `calendar.freebusy`:**

> For business customers, Dialogbot's booking assistant reads only free/busy periods (no event details) to offer callers times when
> the business owner is available.

## 3. Demovideo (YouTube, «Unlisted», på engelsk eller med engelske undertekster)

Google kræver, at videoen viser hele forløbet og OAuth-samtykkeskærmen med **klient-id'et synligt i browserens adresselinje**.

1. Åbn `https://dialogbot.dk/privat`, log ind.
2. Apps → Kalender → «Forbind» ud for Google Kalender.
3. Vis samtykkeskærmen. Zoom på adresselinjen, så `client_id=...` kan læses. Vis app-navnet «Dialogbot» og adgangen.
4. Tryk «Fortsæt» og vis, at man kommer tilbage til Kalender med «Forbundet».
5. Skriv i chatten: «Læg tandlæge torsdag kl. 9 i min kalender». Vis svaret.
6. Åbn Google Kalender i en ny fane og vis, at aftalen står der.
7. Tilbage i Dialogbot: «Fjern fra kalender» på aftalen. Vis i Google Kalender, at den er væk.
8. Vis «Afbryd» ud for Google Kalender (adgangen tilbagekaldes).

Varighed: 2–3 minutter er nok. Skriv i videobeskrivelsen: «Dialogbot only creates, updates and deletes the events it created.»

## 4. Udkast til privatlivspolitikken (afsnit til `legal.json → privacy.sections`)

> **Dialogbot Privat (din personlige assistent)**
>
> Bruger du Dialogbot Privat, behandler vi det, du selv giver os: dine lister, påmindelser og samtaler med assistenten, det
> mobilnummer du bekræfter, og – når du godkender et opkald eller en booking – virksomhedens navn og nummer og det, du har givet
> assistenten lov til at sige. Formålet er at udføre det, du beder om. Grundlag: aftalen med dig (GDPR art. 6, stk. 1, litra b).
>
> **Kalender.** Slår du appen Kalender til, gemmer vi de aftaler, du har godkendt (tidspunkt, sted, hvad der blev aftalt). Forbinder
> du Google Kalender eller Outlook, gemmer vi krypterede adgangsnøgler og bruger dem kun til at oprette, flytte og slette de
> aftaler, Dialogbot selv har lagt i din kalender. Vi læser ikke dine andre aftaler. Du kan afbryde forbindelsen når som helst i
> appen; så tilbagekalder vi adgangen og sletter nøglerne. Laver du et privat kalenderlink, kan alle med linket se dine aftaler i
> Dialogbot; du kan stoppe linket i appen.
>
> **Googles brugerdata.** Dialogbots brug af og overførsel til andre apps af oplysninger modtaget fra Google API'er overholder
> [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), herunder kravene om
> begrænset brug (Limited Use). Vi sælger ikke data fra Google, bruger dem ikke til reklame og bruger dem ikke til at træne
> AI-modeller. Mennesker hos Dialogbot læser dem kun, hvis du beder om det, af sikkerhedsgrunde eller fordi loven kræver det.

Den sidste afsnit (Limited Use) er et krav fra Google og skal stå næsten ordret. Afsnittet skal også under «Hvem hjælper os?», hvis
Google og Microsoft ikke allerede er nævnt som modtagere (de er ikke underdatabehandlere, men modtagere efter brugerens ønske).

## 5. Indsend

Google Auth Platform → Audience → **Publish app** («In production»), derefter Verification Center → **Submit for verification**.
Svar på Googles e-mails i samme tråd; de spørger typisk om videoen eller begrundelsen.

## 6. Microsoft (Outlook)

Microsoft kræver ikke en tilsvarende gennemgang for `Calendars.ReadWrite` i en multi-tenant-app, men brugere i nogle organisationer
skal have administratorens samtykke. «Publisher verification» (Microsoft Partner Network-id) fjerner advarslen «ubekræftet» og
anbefales.
