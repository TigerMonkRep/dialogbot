# Demo-opkald: lad kunden høre Dialogbot

Dialogbot sælges bedst ved, at kunden selv hører assistenten. Der er tre lovlige veje. Alle bruger Dialogbots eget
**salgsarbejdsrum**: dets godkendte viden beskriver Dialogbot, og dets nummer foretager og modtager opkaldene.

| Vej | Hvem tager initiativet | Samtykke |
|---|---|---|
| **Demonummeret** på forsiden | Kunden ringer selv ind | Ikke nødvendigt – kunden ringer selv |
| **"Ring mig op nu"** på forsiden (`#demo`) | Kunden skriver sit nummer og sætter flueben | Fluebenet. Tekst og version gemmes på opkaldet (`demo-call-web-v1`) |
| **Sælgerflowet** `/app/operator/sales` | En Dialogbot-sælger ringer selv (et menneske), spørger "må vores AI ringe dig op nu?" og trykker på knappen ved et ja | Sælgerens bekræftelse. Sælgeren og tidspunktet gemmes og auditeres (`demo-call-seller-v1`) |

## Hvorfor ikke bare lade AI'en ringe kolde opkald?

Markedsføringslovens § 10, stk. 1, forbyder direkte markedsføring med et **automatiseret opkaldssystem**, medmindre
modtageren på forhånd har bedt om det. Reglen siger "nogen" og beskytter derfor også virksomheder. Et opkald, som en
AI foretager og fører uden et menneske i røret, må antages at være et automatiseret opkaldssystem.

- **Robinsonlisten** gælder privatpersoner og er ikke nok. Uanmodede salgsopkald til forbrugere er som udgangspunkt
  forbudt, uanset listen.
- **Reklamebeskyttelse i CVR** skal respekteres, når et menneske ringer til en virksomhed. At en virksomhed ikke er
  reklamebeskyttet, giver ikke lov til at lade en AI ringe.

Derfor gælder samme regel nu for **kampagner**: alle kontakter kræver et dokumenteret samtykke, også virksomheder
(`app/modules/campaigns/service.py`). Kontakter uden samtykke, som blev importeret før ændringen, springes over af
opkaldsmotoren.

> Dette er en teknisk implementering af en juridisk vurdering, som ikke er gennemgået af en advokat. Få den bekræftet
> før drift – også samtykketeksterne (`CONSENT_TEXT_WEB`, `CONSENT_TEXT_SELLER` i `app/modules/sales/service.py`) og
> afsnittet "Demo-opkald" i `/privatliv`.

## Sådan virker det

- **Opkaldet:**
  - Assistenten præsenterer sig som Dialogbots digitale assistent og siger, at kunden selv har bedt om opkaldet.
  - Den tilbyder at være receptionist for kundens egen virksomhed i et rollespil eller at svare på spørgsmål om
    Dialogbot, men kun ud fra salgsarbejdsrummets godkendte viden.
  - Et opkald varer højst 5 minutter.
- **Efter opkaldet:** Opkaldsrapporten bliver klassificeret som en kampagne:
  - *interesseret* eller *ring tilbage*: en henvendelse (kilde `demo_call`) og en opgave med frist om 2 timer i
    salgsarbejdsrummet, plus en notifikation;
  - *ikke interesseret*: en henvendelse uden opgave;
  - *vil ikke ringes op igen*: nummeret kommer på salgsarbejdsrummets spærreliste;
  - intet svar: ingenting.
- **Begrænsninger på hjemmesiden:**
  - kun danske numre (ikke 90-numre);
  - ét opkald pr. nummer pr. døgn;
  - højst `SALES_MAX_CALLS_PER_HOUR` opkald i timen i alt (standard 20);
  - kun mellem `SALES_CALL_FROM` og `SALES_CALL_TO` (standard 08:00–20:00, dansk tid);
  - honeypot-felt mod bots.

  Et nummer på spærrelisten får samme svar som alle andre, men der bliver ikke ringet. Siden afslører altså ikke,
  hvem der har frabedt sig opkald.
- **Sælgerflowet:**
  - Kun for Dialogbot-operatører.
  - Ingen tidsvindue- eller døgngrænse, fordi kunden er i røret lige nu.
  - Med CVR-nummer og konfigureret CVR-adgang bliver en reklamebeskyttet virksomhed afvist.
  - Et nummer på spærrelisten bliver afvist åbent.

## Opsætning (ejer)

1. **Opret salgsarbejdsrummet.** Opret et arbejdsrum "Dialogbot" og læg viden om Dialogbot ind: hvad det er, priser
   (model A og B, kampagnepakker) og hvordan man kommer i gang. Godkend al viden.
2. **Bestil et nummer.** Bestil et nummer til arbejdsrummet via telefoniopsætningen. Som operatør skal du også tillade
   udgående opkald fra nummeret (`/app/operator/telephony` → Afsender).
3. **Sæt miljøvariabler.** Sæt `SALES_WORKSPACE_ID` til arbejdsrummets id på API'et. `VAPI_API_KEY` og
   `VAPI_SERVER_SECRET` skal allerede være sat.
4. **Kontrollér.** Forsiden viser nu demonummeret og formularen. `/app/operator/sales` viser, hvad der eventuelt mangler.
5. **Valgfrit:** `CVR_USERNAME`/`CVR_PASSWORD` giver sælgeren et automatisk tjek af reklamebeskyttelse. Uden dem viser
   siden, at sælgeren selv skal tjekke på datacvr.virk.dk.

## Status

- **Implementeret og testet med simuleret Vapi:** `tests/test_sales_demo_calls.py` og E2E-rejse 1 (forsiden er ærlig,
  når intet er sat op).
- **Ikke eksternt verificeret:** et rigtigt demo-opkald og CVR-feltet `Vrvirksomhed.reklamebeskyttet` mod det
  rigtige CVR-register.
