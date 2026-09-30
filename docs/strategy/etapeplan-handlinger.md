# Etapeplan: "Handlinger, ikke integrationer"

Dato: 30. september 2026. Status: plan for etape 1–5; etape 1 implementeres i samme leverance.

## Baggrund og forbehold

Differentiator A i strategien er, at assistenten *udfører* opgaver i kundens systemer under samtalen – i telefonen
og i webchatten – med bekræftelse til den, der ringer, og et spor i indbakken. Konkurrenterne sælger "integrationer";
Dialogbot sælger handlinger, som kunden kan se og styre.

**Forbehold:** Strategidokumentet `docs/strategy/differentiering-og-handlinger.md` og benchmarkrapporten
`reports/Danske AI telefonassistenter benchmark.md` findes ikke i repoet (heller ikke på andre grene). Etape 1 er
beskrevet fuldt ud i opgaven og er derfor sikker. Etape 2–5 er lagt ud fra opgavens retning og den typiske
systempark hos små danske virksomheder (håndværk, klinik, service, B2B-handel). Rækkefølgen bør justeres, når
strategidokumentets afsnit 5 er tilgængeligt.

## Grundprincipper (gælder alle etaper)

1. **Ærlig status.** En connector vises som `connected` kun, når en legitimation er gemt *og* et testkald mod
   leverandøren er lykkedes. Alt andet er `not_connected`, `error` eller `not_implemented` ("på vej"/"via Zapier").
   Ingen handling udføres uden en `connected` connector.
2. **Handlinger er deklarerede.** Hver handling har navn, dansk beskrivelse, JSON-schema for input og output, og et
   flag for, om kunden i røret skal bekræfte, før den udføres. Input valideres mod schemaet, før adapteren kaldes.
3. **Spor.** Hvert kald logges i `action_runs` (arbejdsrum, samtale, handling, input, output, status, varighed,
   fejltekst, simuleret) og vises i samtalen i indbakken. Legitimationer, tokens og hemmeligheder logges aldrig.
4. **Legitimationer er krypterede** med envelope-kryptering (tilfældig datanøgle pr. række, pakket med en nøgle fra
   miljøet). API-svar indeholder aldrig hemmeligheder – kun booleans, etiketter og udløbstider.
5. **Betaling og viden ændres aldrig af en handling.** Handlinger rører kun eksterne systemer og bookinger/leads/opgaver.
6. **Fakes til test.** Hver adapter har et testdobbelt, der er mærket `simulated` hele vejen ud i API og UI, og som
   nægtes uden for dev/test. Kun rigtige kald mod leverandøren kan give status `connected` i staging/prod.
7. **Lov aldrig en integration, som ikke findes.** Kataloget viser tre ærlige kolonner: klar, på vej, via Zapier/Make.

## Ekstern API-adgang (verificeret 29. september 2026)

Verificeret mod leverandørernes egen udviklerdokumentation. "Offentlig" = enhver kan oprette app/nøgle og kalde
API'et uden aftale (evt. med app-review for at blive vist offentligt). "Partner" = kræver aftale/godkendelse, før
man overhovedet får adgang. "Ukendt" = dokumentationen kunne ikke hentes eller siger det ikke; der er ikke gættet.

| System | Adgang | Kilde (hentet 29.–30/9 2026) | Vigtigste forbehold |
|---|---|---|---|
| Google Calendar API | **Offentlig** | developers.google.com/identity/protocols/oauth2/web-server, …/calendar/api/v3/reference/freebusy/query, …/events/insert, support.google.com/cloud/answer/13461325 | Egen OAuth-klient i Google Cloud. I "Testing": højst 100 testbrugere, og tokens udløber efter 7 dage. Produktion med følsomme scopes kræver OAuth-verificering (privatlivspolitik, domæne, demovideo). Højst 100 refresh tokens pr. konto pr. klient; udløber efter 6 mdr. inaktivitet. |
| Microsoft Graph (kalender) | **Offentlig** | learn.microsoft.com/entra/identity-platform/v2-oauth2-auth-code-flow, …/graph/permissions-reference, …/publisher-verification-overview | App-registrering i Entra, multitenant. `Calendars.ReadWrite` kræver ikke admin-samtykke, men tenants med risikobaseret samtykke blokerer ikke-verificerede multitenant-apps → *publisher verification* anbefales. `getSchedule` virker kun for arbejds-/skolekonti; vi bruger derfor `calendarView`. PKCE anbefales for alle klienttyper. |
| Twilio SMS til Danmark | **Offentlig** | twilio.com/en-us/guidelines/dk/sms | Alfanumerisk afsender understøttet, *ingen forhåndsregistrering*. Danske long codes understøtter SMS og tovejs-SMS. |
| Zapier – Webhooks by Zapier | **Offentlig** (betalt plan) | help.zapier.com/hc/en-us/articles/8496288690317 | "Catch Hook" findes kun på Professional/Team/Enterprise – ikke gratisplanen. JSON; højst 10 MB. |
| Make – custom webhooks | **Offentlig** | help.make.com/webhooks | Højst 300 anmodninger pr. 10 sek. (ellers 429); kø-loft efter plan. Siden siger ikke, om gratisplanen er med. |
| e-conomic (Visma) | **Partner** | e-conomic.com/developer | Kræver en *developer agreement* (tilmelding), før app-tokens kan udstedes; gebyr nævnes ikke. |
| HubSpot | **Offentlig** (med forbehold) | developers.hubspot.com/docs/api/creating-an-app | Apps kan installeres uden Marketplace-listing, men uverificerede apps vises med advarsel. Review kun for listing. |
| Pipedrive | **Offentlig** (API-token/OAuth) | developers.pipedrive.com/docs/api/v1 | API-token pr. kunde og OAuth findes. Om OAuth til egne kunder kræver Marketplace-review, fremgår ikke → **ukendt**. |
| Dinero, Billy, Ordrestyring, Minuba, Planday, SimplyBook.me, Calendly, EasyPractice, Microsoft Bookings, GatewayAPI | **Ukendt** | – | Ikke verificeret: researchen blev afbrudt, før siderne blev hentet. Verificeres, før etape 2–4 planlægges i detaljer. |


## Etape 1 – Handlinger-fundament (denne leverance)

### Omfang
- Connector-register med status pr. arbejdsrum (`not_connected | connected | error | not_implemented`) og
  deklarerede handlinger.
- Krypterede legitimationer pr. arbejdsrum; OAuth 2.0 (authorization code + PKCE + state) for Google Calendar og
  Microsoft 365; API-nøgle/webhook-hemmelighed for webhook-connectoren.
- Fælles tool-builder, der bruges af både Vapi-assistenten (telefon) og webchatten. AI-udbyderen udvides med
  tool use (i dag er den kun tekst). Kun handlinger fra `connected` connectors eksponeres.
- `action_runs` med visning i indbakkens samtale.
- Tre connectors med rigtige adaptere bag interface + fake: (a) Google Calendar og Microsoft 365-kalender –
  ledige tider, opret, flyt, aflys; erstatter iCal-koblingen for kunder, der forbinder via OAuth, ellers iCal;
  (b) udgående webhook med HMAC-signatur i Zapier/Make-kompatibelt format med retry via outbox-workeren;
  (c) SMS-bekræftelse via Twilio (platformens konto/underkonto) som handlingen `send_sms_bekraeftelse` med
  skabeloner, der kun kan indeholde godkendt viden og samtaleoplysninger.
- Frontend: `/app/settings/integrationer` (katalog, forbind/afbryd, status, seneste handlinger); handlinger i
  samtalevisningen; valgfrit guide-trin "Forbind jeres systemer", der aldrig blokerer aktivering.

### Datamodel
| Tabel | Formål |
|---|---|
| `integration_connections` | Én række pr. (arbejdsrum, connector): status, `auth_kind`, krypteret hemmelighed (`key_version`, `wrapped_dek`, `nonce`, `ciphertext`), ikke-hemmelig `config` (fx kalender-id, afsendernavn, webhook-URL), `account_label`, `scopes`, `expires_at`, `error`, `version`, `connected_by`, `connected_at`, `last_ok_at`. |
| `oauth_states` | Kortlivet PKCE/state pr. forbindelsesforsøg: `state` (nøgle), arbejdsrum, connector, bruger, krypteret `code_verifier`, `expires_at`, `used_at`. |
| `action_runs` | Spor pr. handlingskald: arbejdsrum, samtale (valgfri), kanal, connector, handling, input, output, status (`ok | failed | refused | simulated`), `duration_ms`, fejltekst, `provider_ref`. |
| `bookings` (+2 kolonner) | `calendar_connector` og `calendar_event_id`, så en booking kan flyttes/aflyses i kundens kalender. |
| `outbox_events` | Ny hændelsestype `webhook.deliver` (ingen skemaændring). |

### Nye endpoints (alle under `/workspaces/{workspace_id}/…` medmindre andet nævnes)
| Metode og sti | Beskrivelse |
|---|---|
| `GET /integrations` | Katalog: hver connector med status, handlinger, om den er simuleret, og hvad der mangler. |
| `POST /integrations/{key}/connect` | OAuth: svarer med `authorize_url`. Nøgle/webhook/SMS: tager konfiguration, tester forbindelsen og gemmer. Idempotency-Key. |
| `GET /integrations/oauth/{key}/callback` (uden arbejdsrum) | Leverandørens redirect. Slår `state` op, bytter kode med PKCE, gemmer krypteret, sender brugeren tilbage til frontend. |
| `PUT /integrations/{key}` | Ikke-hemmelig konfiguration (`version`/`expected_version`). |
| `POST /integrations/{key}/test` | Testkald mod leverandøren (webhook: sender en testhændelse). Idempotency-Key. |
| `DELETE /integrations/{key}` | Afbryd: tilbagekald token (best effort), slet hemmelighed, audit. |
| `GET /integrations/actions` | Seneste `action_runs`. |
| `GET /conversations/{id}` (+`actions`) | Samtalen leverer nu også handlingerne i tidsorden. |

### Frontend
- `/app/settings/integrationer` med fane i indstillingerne: tre kolonner (klar / på vej / via Zapier eller Make),
  kort pr. connector med status, forbind/afbryd, konfiguration, testknap og seneste handlinger.
- Indbakke: handlinger vises som egne kort i samtalens tidslinje ("Booket … i Google Kalender", "SMS sendt til …").
- Guide: valgfrit trin "Forbind jeres systemer" (`/app/settings/integrationer`), aldrig blokerende.

### Tests
- Register: status pr. arbejdsrum, `not_implemented` når miljøet mangler klient-id.
- Kryptering: rundtur, nøglerotation, at hemmeligheden aldrig kan læses via API'et eller optræder i logs.
- OAuth: state kan kun bruges én gang, udløber, og afvises for et andet arbejdsrum; PKCE-verifier sendes ved byttet.
- Tool-builder: kun handlinger fra `connected` connectors; ugyldigt input afvises før adapteren; `action_runs`
  skrives også ved fejl; samme kald i Vapi og webchat.
- Webhook: signatur kan verificeres; retry via outbox med backoff; fejl efter max forsøg vises på connectoren.
- SMS: skabelon kan ikke indeholde fri tekst fra modellen; sendes fra arbejdsrummets nummer/afsender.
- Fakes er mærket `simulated` i API-svar og `action_runs`.

### Risici
- Google kræver OAuth-verificering for følsomme scopes; indtil da er appen i "testing" med brugerloft. Se tabellen.
- Microsoft: multi-tenant app kræver "publisher verification" for at slippe for advarsler hos kunden.
- Tool use i telefonen giver latenstid pr. kald (Vapi venter på vores webhook). Handlinger skal svare < 3 s.
- SMS: Twilio tillader alfanumerisk afsender i Danmark uden registrering; vi bruger det som standard (≤ 11 tegn).
- Model-hallucinerede parametre: derfor schema-validering, `bekraeftet`-flag og korte, eksplicitte beskrivelser.

### Bevidst ikke med i etape 1
- CRM- og økonomisystemer (etape 2–3), fagsystemer og bookingplatforme (etape 4).
- Indgående webhooks (at eksterne systemer skubber data ind).
- Medarbejdergodkendelse af handlinger før udførelse (etape 5).
- Google/Microsoft *Contacts* og *Mail* – kun kalender.
- Flere kalendere pr. arbejdsrum (én primær kalender pr. connector).
- Zapier som *offentlig* app (kun webhook-format, som Zapier/Make forstår).

## Etape 2 – Kend kunden: CRM-opslag og notater

### Omfang
- Connectors: HubSpot (OAuth), Pipedrive (OAuth/API-token). Via Zapier/Make for resten.
- Handlinger: `find_kunde` (på telefonnummer/e-mail – bruges ved opkaldets start, så assistenten kender kunden),
  `opret_kunde`, `noter_henvendelse` (aktivitet/notat på kunden), `opret_opgave_i_crm`.
- Lead-synk: en godkendt henvendelse i Dialogbot skrives som kontakt/deal i CRM'et (via outbox, idempotent).
- Bekræftelse: opslag kræver ikke bekræftelse; oprettelse og notater gør det ikke heller, men vises i indbakken.

### Datamodel
- `integration_connections.config` udvides med feltmapping (hvilket CRM-felt er telefon, kilde, ejer).
- `leads` får `external_ref` (jsonb: connector, id, url) og `synced_at`.
- `action_runs` uændret.

### Endpoints
- `POST /integrations/{key}/mapping` (PUT-semantik med version) til feltmapping.
- `POST /leads/{id}/sync` (manuel synk) og outbox-hændelse `crm.sync_lead`.

### Frontend
- Integrationskort for CRM med mapping-editor; på henvendelsen vises "Findes i HubSpot" med link.
- I samtalen: "Kendt kunde: …" som første handling.

### Tests
- Opslag ved samtalestart (fake CRM), oprettelse er idempotent, mapping validering, synk-retry.

### Risici
- HubSpot-apps skal gennem review for at blive listet; til egne kunder er en "public app" uden listing nok.
- Persondata: CRM-opslag på telefonnummer er behandling af personoplysninger – skal i databehandleraftalen.

### Bevidst ikke med
- To-vejs synk (ændringer i CRM tilbage til Dialogbot). Deals/pipeline-styring. Salesforce og Dynamics (partner/enterprise).

## Etape 3 – Penge og ordrer: økonomisystemer

### Omfang
- Connectors: e-conomic, Dinero, Billy (alle med token/OAuth ifølge tabellen).
- Handlinger: `find_faktura` (status, forfaldsdato, beløb – kun til kunden selv efter verifikation af telefon/e-mail),
  `send_fakturakopi` (via systemets egen udsendelse), `opret_tilbudskladde`/`opret_ordrekladde` (kræver bekræftelse).
- Kundekartotek i økonomisystemet bruges som fallback til `find_kunde`.

### Datamodel
- `integration_connections.config`: standardkonti/layout, om kladder må oprettes.
- `action_runs.output` med beløb; ingen kortdata nogensinde.

### Endpoints
- Ingen nye ud over connect/test/mapping. Handlingerne kommer via tool-builderen.

### Frontend
- Kort pr. system, valg af hvilke handlinger der er slået til (fx kun opslag, ikke kladder).

### Tests
- Verifikation af, at fakturaoplysninger kun gives til matchende kunde; kladde kræver `bekraeftet`; beløb formateres dansk.

### Risici
- Adgangsmodellerne afviger (se tabellen); e-conomic kræver en udvikleraftale før der kan udstedes app-tokens.
- Fejlagtige økonomiske oplysninger i telefonen er dyre – derfor kun læsning og kladder, aldrig bogføring.

### Bevidst ikke med
- Bogføring, betalinger, rykkere, kreditnotaer. Automatisk fakturering ud fra samtaler.

## Etape 4 – Fagsystemer og bookingplatforme

### Omfang
- Booking i kundens eget system i stedet for Dialogbots kalender: Microsoft Bookings (Graph), SimplyBook.me,
  Calendly, EasyPractice (hvis API findes – se tabellen). Handlinger som i etape 1, men mod systemet.
- Håndværk: Ordrestyring og Minuba (kun hvor API-adgang findes): `opret_sag`, `find_sag_status`.
- Vagtplan: Planday `hvem_er_paa_vagt` (til korrekt tilbagekald/omstilling).

### Datamodel
- `bookings.calendar_connector` dækker allerede fremmede systemer; `external_ref` på opgaver.

### Endpoints
- Ingen nye typer; connectors erklærer sine handlinger.

### Frontend
- Valg af "primær bookingkilde" pr. arbejdsrum (Dialogbot / eksternt system).

### Tests
- Kun én bookingkilde aktiv; konflikt ved samtidig booking; faglige handlinger kræver bekræftelse.

### Risici
- Flere af systemerne er partnerstyrede eller uden offentlig API; de vises som "på vej" eller "via Zapier".

### Bevidst ikke med
- Systemer uden dokumenteret API. Skærmautomatisering/RPA.

## Etape 5 – Godkendelse, egen connector og drift i skala

### Omfang
- Medarbejdergodkendelse: handlinger kan kræve "godkend før udførelse" (kø i indbakken, SMS/notifikation), med
  tidsfrist og fallback-besked til kunden.
- Kundedefineret connector: kunden beskriver et HTTP-endpoint (URL, headers, JSON-schema) og får en handling.
- Handlingsstatistik og fejlovervågning pr. connector; automatisk pause ved gentagne fejl.
- Zapier/Make som offentlige apps (triggers + actions), så Dialogbot findes i deres kataloger.

### Datamodel
- `action_runs.status` får `pending_approval | approved | rejected | expired`; `action_approvals`-tabel.
- `custom_connectors` (definition, version, godkendt af).

### Endpoints
- `POST /actions/{id}/approve|reject`; CRUD for `custom-connectors`.

### Frontend
- Godkendelseskø; connector-bygger med testkald.

### Tests
- Godkendelse udløber; afvist handling giver kunden en ærlig besked; custom connector kan ikke nå private adresser (SSRF).

### Risici
- Kundedefinerede endpoints er en angrebsflade (SSRF, datalæk). Kræver allowlist, timeouts, størrelseslofter.

### Bevidst ikke med
- Kodeeksekvering, filupload til eksterne systemer, betalingshandlinger.

## Spørgsmål, der kræver beslutning (blokerer ikke etape 1's kode)

1. OAuth-klienter: Google Cloud-projekt (OAuth consent screen, redirect-URI) og Microsoft Entra app-registrering –
   hvem ejer dem, og hvilket domæne/privatlivspolitik skal opgives?
2. Skal SMS afsendes som alfanumerisk afsender ("Dialogbot" eller kundens navn ≤ 11 tegn) eller fra et nummer?
3. Hvilke systemer i etape 2–4 skal prioriteres, når strategidokumentet foreligger?
4. Partneraftaler (se tabellen): hvem tager kontakten?
