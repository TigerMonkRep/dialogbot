# Ejerguide – det skal Dialogbot selv konfigurere

Kunderne skal ikke gøre noget af dette. Det er Dialogbots egne konti. Hemmeligheder sættes kun i Render
(Environment) og aldrig i Git, chat eller Vercel.

## 1. Twilio (hovedkonto, dansk nummer)

1. Opret eller brug Dialogbots Twilio-konto, og opgrader den fra trial, da trial-konti ikke kan købe danske numre
   til kunder.
2. Opret en **API-nøgle** under Account → API keys & tokens (Standard). Gem SID og secret.
3. Tjek grænsen for underkonti på kontoen (Twilio har et loft pr. konto; det kan hæves via support). Hvert
   arbejdsrum bruger én underkonto.
4. Dokumentation til danske lokalnumre (Regulatory Compliance → Bundles):
   - For hver kunde laves et bundle af typen *business* med virksomhedsnavn, CVR, adresse og den uploadede
     CVR-udskrift (ses i `/app/operator/telephony` → "Se dokument").
   - Når Twilio har godkendt bundlet, indsættes `BU…`-SID'en under "Godkend dokumentation".
   - Den første uge kan det være manuelt. Automatisering via Twilios Regulatory API er næste skridt (se
     "Ikke implementeret").
   - Alternativ: sæt `TELEPHONY_NUMBER_TYPE=mobile`. Danske mobilnumre kræver kun oplysninger, ingen dokumenter, men
     prisen er typisk højere. Tjek den gældende pris, før I skifter.
5. Tjek prisen på et dansk lokalnummer og pr. minut i Twilio Console → Pricing, før I sætter
   `TELEPHONY_PROVIDER=live`. Hvert "Forbind telefonen" køber ét nummer.

## 2. Vapi (Dialogbots organisation)

1. `VAPI_API_KEY`: den **private** nøgle (Organization → API Keys).
2. `VAPI_SERVER_SECRET`: vælg en tilfældig værdi på mindst 32 tegn. Dialogbot sætter den selv som Bearer-header,
   når numre importeres.
3. `VAPI_ORG_ID`: organisationens id. Så afvises webhooks fra andre organisationer.
4. Kontrolopkald: køb eller importér ét platformnummer i samme Vapi-organisation, og sæt dets Vapi-id i
   `TELEPHONY_VERIFY_NUMBER_ID`. Nummeret bruges kun til at læse koder op.

## 3. Render (API **og** worker)

| Variabel | Værdi |
|---|---|
| `TELEPHONY_PROVIDER` | `live` (først når punkt 1–2 er klar; uden den står alle kunder som "Forbindelse klargøres – venter på Dialogbot") |
| `TWILIO_ACCOUNT_SID` | `AC…` (hovedkonto) |
| `TWILIO_API_KEY_SID` / `TWILIO_API_KEY_SECRET` | fra punkt 1.2 (alternativt `TWILIO_AUTH_TOKEN`) |
| `TELEPHONY_NUMBER_COUNTRY` / `TELEPHONY_NUMBER_TYPE` | `DK` / `local` (standard) eller `mobile` |
| `VAPI_API_KEY`, `VAPI_SERVER_SECRET`, `VAPI_ORG_ID`, `TELEPHONY_VERIFY_NUMBER_ID` | fra punkt 2 |
| `PUBLIC_BASE_URL` | allerede sat. Bruges som webhook-adresse ved import |

Vercel og Supabase skal ikke have nye variabler. Frontenden kalder kun `/api/backend/*`, og dokumenter ligger i det
eksisterende private lager (`VOICE_STORAGE`).

## 4. Første rigtige test (skal dokumenteres)

1. Giv dig selv operatørrollen: `python -m scripts.grant_operator grant <din e-mail>`.
2. Opret et testarbejdsrum, og gennemfør de fem trin med dit eget mobilnummer.
3. Godkend dokumentationen i `/app/operator/telephony`, og tryk "Kør klargøring nu".
4. Viderestil din mobil med `**61*<Dialogbot-nummer>#`. Start et prøveopkald, og ring til din mobil fra en anden
   telefon uden at tage den.
5. Notér opkalds-id, tidspunkt og resultat i `docs/telephony/README.md` under "Test". Slå viderestillingen fra med
   `##002#`.

## Ikke implementeret (kræver beslutning eller budget)

- **Automatisk oprettelse af Twilio-bundles** via Regulatory API. I dag godkender operatøren manuelt med bundle-SID.
- **Nyt nummer eller nummerflytning** til Dialogbot. Kunden kan markere ønsket; operatøren følger op. Der er intet
  automatisk flow.
- **Frigivelse af numre**, når en kunde stopper. Bevidst ikke automatiseret: numre slettes aldrig som oprydning.
- **Prisimport** fra Twilio Pricing API. Købsomkostningen registreres uden beløb (`amount_micros = NULL`).
