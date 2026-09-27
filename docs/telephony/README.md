# Telefoni – platformadministreret drift

Dato: 27. september 2026. Branch: `claude/cool-wozniak-ho00tr`.

## Årsag til fejlen på `/app/settings/telephony`

Fejlen lå ikke kun i teksten. Backend var bygget til kundeejede leverandørkonti:

- `phone_numbers` var dokumenteret som *"The number is bought/imported at the provider by the customer; this row
  only maps it"*.
- `POST /workspaces/{ws}/phone-numbers` lod kundens administrator indtaste et E.164-nummer og Vapis
  `provider_number_id`.
- `GET /phone-numbers` returnerede `webhook_url` og `configured = bool(VAPI_SERVER_SECRET)`. Det var den flag, der
  viste "Stemmeforbindelse konfigureret", selvom arbejdsrummet ikke havde noget nummer.
- Webhook-routingen faldt tilbage fra et ukendt Vapi-nummer-id til opslag på E.164.
- Opsætningskontrollen "prøveopkald" blev godkendt af ethvert opkald inden for 30 dage.
- Kampagner ringede ud med kundens indtastede nummer-id som afsender.
- Nummersiden bad kunden hente et ElevenLabs-stemme-id "via jeres Vapi-konto".

## Ny arkitektur

| Del | Hvem ejer den | Hvor |
|---|---|---|
| Twilio-hovedkonto og API-nøgle | Dialogbot | Render (hemmeligheder) |
| Twilio-underkonto pr. arbejdsrum (forbrug afregnes til hovedkontoen) | Dialogbot | `telephony_accounts` (kun SID, ingen hemmeligheder) |
| Dialogbot-nummer (destination) pr. arbejdsrum | Dialogbot | Twilio-underkontoen + `phone_numbers` (`source=platform`) |
| Import i Vapi med webhook og Bearer-hemmelighed | Dialogbot | Vapi-organisationen (`VAPI_API_KEY`) |
| Kundens eget nummer | Kunden, hos sit teleselskab | `telephony_setups.business_number`. Viderestilles til destinationen |
| Virksomhedsdokumentation (dansk lokalnummer) | Kunden uploader, Dialogbot indsender | Privat lager + `telephony_setups` |

Kunden ser kun sit Dialogbot-nummer og en guide til viderestilling. Kunden ser aldrig konti, id'er, nøgler eller
webhooks.

### Kundens forløb (`/app/settings/telephony`)

1. **Dit nuværende nummer.** Kunden angiver nummer, abonnementstype, teleselskab og hvornår der skal viderestilles.
   Nummeret bekræftes med et kontrolopkald: Dialogbot ringer op fra et platformnummer og læser en 6-cifret kode op.
   Koden gemmes som HMAC, gælder i 10 minutter og tillader højst 5 forsøg og 3 opkald i timen. For danske
   lokalnumre indtaster kunden desuden virksomhedsnavn, CVR og adresse og uploader en CVR-udskrift (Twilios krav:
   virksomhedsregistrering med dansk adresse).
2. **Forbind telefonen.** Kræver bekræftet nummer, dokumentation og en valgt prisaftale. Først da oprettes et
   provisioneringsjob. Når nummeret er klar, vises en viderestillingsguide pr. abonnementstype:
   - mobil: GSM-standardkoder (3GPP TS 22.030: `**61*`, `**67*`, `**62*`, `**21*`, `##002#`);
   - fastnet og omstilling: fremgangsmåde uden opdigtede koder.
3. **Sådan skal vi svare.** Tjekliste med links til stemme, velkomst, åbningstider og hvad der sker, hvis stemmen
   fejler. Hilsen og talestil kan sættes for telefonen.
4. **Test forbindelsen.** Kunden starter et prøveopkald, der gælder i 15 minutter, og ringer til sit eget nummer.
   Testen består kun, hvis opkaldet ramte arbejdsrummets destination, blev gemt i arbejdsrummets indbakke og
   varede mindst 3 sekunder. Et opkald fra et Dialogbot-nummer afvises som loop. Tests i simuleret tilstand
   bliver registreret med `simulated=true`.
5. **Aktivér.** Kan kun ske efter et bestået prøveopkald og en valgt prisaftale. Før aktivering, og under pause,
   hører opkaldere kun en kort besked. Assistenten svarer ikke.

Statusserne udledes af data og står aldrig som "Aktiv" alene, fordi en nøgle er sat:

| Kode | Label |
|---|---|
| `not_started` | Ikke sat op |
| `awaiting_info` | Afventer oplysninger |
| `provisioning` | Forbindelse klargøres |
| `ready_for_test` | Klar til prøveopkald |
| `test_failed` | Test fejlede |
| `active` | Aktiv |
| `paused` | Sat på pause |

### Provisionering (idempotent)

`telephony_jobs` har én række pr. arbejdsrum med idempotensnøglen `dialogbot-<workspace id>`. Jobbet køres af
workeren hvert minut og første gang med det samme, når kunden trykker "Forbind telefonen". Trin for trin:

1. Find eller opret underkontoen (FriendlyName = nøglen).
2. Vent på godkendt dokumentation (`documents_status=approved` + bundle-SID). Status: venter, ikke fejl.
3. Find et nummer i underkontoen med FriendlyName = nøglen, og adoptér det. Ellers køb præcis ét. `purchase_started`
   gemmes, *før* købet sker. Efter en timeout bliver der aldrig købt igen: jobbet venter på afstemning og markerer
   jobbet som fejlet efter 6 forsøg, så en operatør kan kigge.
4. Find nummeret i Vapi, og adoptér det. Ellers importér det med vores webhook-URL og Bearer-hemmelighed. Auth-token
   for underkontoen hentes kun i selve importkaldet og gemmes ikke.
5. Opret `phone_numbers` (`source=platform`, `status=active`) og bind den til `telephony_setups`.

Fejl bliver prøvet igen med backoff (1, 5, 15, 60, 240 minutter). Tekniske fejl ses kun i operatørvisningen.

### Routing og webhooks

`POST /api/v1/webhooks/vapi` kræver Bearer-hemmeligheden, sammenlignet i konstant tid. Derudover
(`platform.route`):

- Er `VAPI_ORG_ID` sat, afvises opkald fra en anden Vapi-organisation.
- Et ukendt `phoneNumberId` matches **aldrig** på nummer i stedet.
- Et id og et nummer, der ikke passer sammen, afvises.
- Kun numre med `status=active` routes. Ukendt routing får et fejlsvar og tilfalder aldrig et andet arbejdsrum.
- Opkaldsrapporter er idempotente pr. opkalds-id, og det har de altid været.

### Udgående opkald

En kampagne kan kun starte, når dens nummer har `outbound_allowed=true`. Det sætter en operatør, når Twilio
tillader afsenderen for kunden. Viderestilling af et indgående nummer giver ikke tilladelse til udgående
caller-ID. Kampagnelancering, fravalg og forbrugsgrænser er uændrede.

### Omkostninger

`telephony_costs` registrerer leverandøromkostninger pr. arbejdsrum: Vapis `cost` pr. opkald i USD (mikro-enheder)
og nummerkøb. De er kun interne og indgår aldrig i kundens faktura, som følger kundens Dialogbot-aftale.

## Operatør (`/app/operator/telephony`, kun `is_platform_operator`)

Der findes ikke noget `/admin`-område i frontenden. Platformoperatørernes område er `/app/operator/…`, låst til
rollen `is_platform_operator`, som er adskilt fra virksomhedens administrator.

Operatøren kan:
- se konfigurationen, kun som "sat" eller "mangler";
- se job, trin, fejl og forsøg;
- bekræfte et nummer manuelt med begrundelse;
- se kundens dokument og godkende det med Twilio-bundle-SID eller afvise det;
- køre et job nu;
- tilknytte et eksisterende nummer til migrering;
- give tilladelse som afsender.

Alle handlinger bliver auditeret.

## Test (27/9 2026)

| Test | Resultat |
|---|---|
| `tests/test_telephony_platform.py` (5) | **Bestået.** En ny kunde gennemfører hele forløbet uden leverandørlogin. To arbejdsrum får hver deres underkonto og nummer. Fremmed org, ukendt id, id/nummer-uoverensstemmelse og loop afvises. Timeout efter køb, import og underkonto giver præcis ét køb, én import og én underkonto, også ved gentagne klik. Uden platformkonfiguration er statusserne ærlige, og der gives kontrolopkald 503 og manuel bekræftelse. Kampagnens afsender kræver operatørtilladelse. Ingen id'er eller hemmeligheder i kundens svar. |
| `tests/test_telephony.py`, `test_campaigns.py`, `test_bookings.py`, `test_reception_script.py`, `test_voices.py` | **Bestået** efter omlægning til operatørtilknyttede numre |
| E2E rejse 14 (desktop + mobil) | **Bestået.** Kunden gennemfører alle fem trin i browseren med simuleret leverandør. Siden indeholder ikke "Vapi", "Twilio", "webhook", "Bearer", "API-nøgle" eller "nummer-id". Et prøveopkald ender i indbakken og som henvendelse |
| Rigtig viderestilling og rigtigt indgående opkald | **Ikke udført.** Kræver Dialogbots Twilio-konto og et godkendt dansk nummer (se ejerguiden) |

Alle leverandørkald i testene er **simulerede** (`TELEPHONY_PROVIDER=fake`, kun tilladt i dev og test).
