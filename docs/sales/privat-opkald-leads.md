# Privat-opkald som lead-kilde: afslutningslinjen

Når Dialogbot Privat ringer til en virksomhed på en privatkundes vegne, kan opkaldet (når reglerne tillader det) afsluttes med **én kort, ærlig
sætning** om Dialogbot. Siger virksomheden ja til en mail og giver adressen, bliver den et lead i salgsarbejdsrummet. Siger den nej, bliver den spærret.
Hensigten er, at brugerens ærinde **aldrig** lider under det.

> **Status:** bygget og testet med simuleret Vapi (`tests/test_lead_pitch.py`). **Slået fra** (`LEAD_PITCH_ENABLED=false`).
> **Ikke eksternt verificeret:** ingen rigtig Vapi-samtale (værktøjskaldene er bygget ud fra Vapis dokumenterede format og ikke prøvet mod den rigtige tjeneste),
> intet rigtigt CVR-opslag, og **den juridiske vurdering er ikke gennemgået af en jurist** (se «Juridisk forbehold»).

## Reglerne (håndhævet i kode)

Linjen siges kun, når **alle** disse holder:

| # | Regel | Hvor |
|---|---|---|
| 1 | Opkaldet er startet af en Privat-bruger. Kampagne- og demo-opkald har andre assistenter og får hverken værktøjet eller teksten | `calls.assistant_for`; værktøjet findes kun der |
| 2 | Brugerens ærinde er afsluttet: aftalen er bekræftet af assistenten (dag og klokkeslæt gentaget) eller afvist, og opkaldet er besvaret | `lead_pitch._say_line` (`errand_outcome` = `confirmed`/`declined`) |
| 3 | Virksomheden er ikke Dialogbot-kunde (CVR og telefon mod `business_profiles`, `phone_numbers`, `telephony_setups`) | `lead_pitch.is_dialogbot_customer` |
| 4 | Virksomheden er ikke på spærrelisten (telefon/CVR) | `lead_pitch.eligibility` |
| 5 | Der er ikke sagt en linje til samme virksomhed inden for `LEAD_PITCH_COOLDOWN_DAYS` (standard 90). Nedtællingen starter, når linjen *siges* | `ExternalBusinessContact.last_pitch_at` |
| 6 | Virksomheden er ikke **reklamebeskyttet** i CVR. **Ukendt tæller som beskyttet** | `advertising_protected` (`None` → springes over) |
| 7 | Virksomheden er rolig. Er den stresset, har travlt, lægger den på, eller er samtalen gået dårligt, springes linjen over; den afbryder aldrig | `business_is_calm`, rapportens `endedReason` |

Reglerne tjekkes **to gange**: da opkaldet sættes op (så værktøjet slet ikke gives til assistenten, hvis de ikke holder) og igen, når assistenten beder
om linjen. Er `LEAD_PITCH_ENABLED=false`, sker der ingenting, og der logges ingenting.

## Teksten

Linjen er en **fast tekst**, ikke AI-genereret (samme princip som SMS-skabelonerne). Den ligger i én konstant, `lead_pitch.PITCH_LINE`, og testen låser ordlyden:

> «Tak for hjælpen. Jeg ringer på vegne af en kunde via Dialogbot – hvis I vil høre, hvad det kan gøre for jeres telefon, sender vi gerne en mail. Ellers ingen problem, hav en god dag.»

Kun verificerede fakta: ingen priser, ingen procenter, ingen «bedst». Det samme gælder svarlinjerne (`ASK_EMAIL_LINE`, `THANKS_LINE`, `DECLINE_LINE` …) og intro-mailen
(`email_templates.intro_mail`). Assistenten får teksten som svar fra værktøjet `end_call_pitch` og skal sige den **ordret**. Står den ikke ordret i udskriften, trækkes samtykket tilbage
(`line_not_verbatim`): en omskrevet linje er ikke det tilbud, virksomheden kan have sagt ja til.

## Forløbet

1. `end_call_pitch(errand_outcome, business_is_calm)`: reglerne tjekkes. Er de opfyldt, svarer værktøjet med teksten; cooldown og `pitch_started_at` sættes.
2. Virksomheden svarer. `pitch_reply(interested, email?)`:
   - **Ja + gyldig adresse** (valideres, og en ugyldig gemmes ikke): `consent_to_email=true`, adressen og tidspunktet gemmes, og der oprettes eller opdateres **ét lead** i `SALES_WORKSPACE_ID`
     (kilde `privat_call`) med en opgave «Send intro-mail til …» (frist: næste dag).
   - **Ja uden adresse**: intet lead, ingen adresse.
   - **Nej / «ikke interesseret»**: virksomheden spærres (`declined_pitch`, telefon + CVR på spærrelisten). Der gemmes **kun** spærringen og datoen: ingen adresse, intet lead, ingen opfølgning.
3. Ved opkaldsrapporten klippes afslutningen væk fra udskriften, **før** ærindet vurderes. Linjen kan derfor aldrig ændre `confirmed_text`, `business_reply` eller prisen.

## Hvad der gemmes

| Hvor | Hvad |
|---|---|
| `private_calls` | `pitch_outcome` (`interested`/`declined`/`skipped`/`not_asked`), `pitch_skipped_reason`, `pitch_transcript_excerpt` (kun afslutningen, højst 500 tegn), `pitch_started_at` |
| `external_business_contacts` | CVR, telefon, navn, hjemmeside, bookingmotor (`booking_profile_id`), `is_dialogbot_customer`, spærring + årsag, `last_pitch_at`, `pitch_count`, `last_outcome`, `email` + `consent_to_email` + `consent_at` (**kun** efter ja), `lead_id` |
| Leadet | Kilde «Privat-opkald», **kategori** («værksted», «frisør» …, aldrig navn), bookingmotor, udfaldet, uddrag af afslutningen og næste skridt «Send intro-mail». Intet om brugeren eller ærindet |

Der oprettes aldrig et lead, og en e-mailadresse gemmes aldrig, uden udtrykkeligt ja. Samme virksomhed giver ét lead: en gentagelse opdaterer det (på lead-id, ellers på telefon).

Skip-årsager: `dialogbot_customer`, `blocklisted`, `cooldown`, `advertising_protected`, `advertising_unknown`, `no_number`, `call_not_answered`, `counterparty_ended`, `errand_not_finished`, `stressed`,
`hung_up_during_pitch`, `no_reply`, `line_not_verbatim`; `not_asked` med `assistant_did_not_ask`.

## Operatørfladen

`/app/operator/sales`, sektionen «Kilde: Privat-opkald» (API: `GET /operator/sales/privat-leads`): virksomhed, kilde, udfald, cooldown-dato og to knapper. **Kun admin og ejer i salgsarbejdsrummet**
(andre får 404, medlemmer under admin 403).

- **Send intro-mail** sender den faste mail (`email_templates.intro_mail`) gennem den almindelige outbox og mailadapter, kun til en adresse, der er givet med ja, og kun én gang. Leadet bliver «kontaktet», og opgaven lukkes.
- **Spær** sætter virksomheden på spærrelisten (telefon + CVR), og den gemte adresse og samtykket slettes.

## Drift

| Variabel | Standard | Betydning |
|---|---|---|
| `LEAD_PITCH_ENABLED` | `false` | Slår linjen til. **Sæt den ikke i prod, før en jurist har bekræftet vurderingen nedenfor** |
| `LEAD_PITCH_COOLDOWN_DAYS` | `90` | Hvor længe samme virksomhed ikke får linjen igen |
| `SALES_WORKSPACE_ID` | – | Arbejdsrummet, leadet oprettes i. Uden det oprettes der intet lead (samtykket gemmes stadig) |
| `CVR_USERNAME` / `CVR_PASSWORD` | – | Uden adgang til CVR er reklamebeskyttelsen ukendt, og linjen springes over (`advertising_unknown`) |

## Juridisk forbehold

Opkaldet er **bestilt af en privat kunde** og har et ærinde for kunden. Men **afslutningslinjen har et markedsføringsformål**: den gør virksomheden opmærksom på Dialogbot. Det rejser to spørgsmål, som ikke er afklaret:

- **Markedsføringslovens § 10.** Direkte markedsføring med et automatiseret opkaldssystem kræver forudgående samtykke (se `docs/sales/demo-calls.md`). Om en sætning i slutningen af et kundebestilt opkald er direkte markedsføring, og om en AI-assistent, der ringer, er et automatiseret opkaldssystem i den forstand, er ikke afgjort.
- **Reklamebeskyttelse i CVR.** Er virksomheden reklamebeskyttet, springes linjen over. Ukendt behandles som beskyttet. At en virksomhed ikke er reklamebeskyttet, giver ikke i sig selv lov til at markedsføre.

**Vurderingen skal bekræftes af en jurist, før `LEAD_PITCH_ENABLED` sættes i prod.** Det gælder også teksten, svarlinjerne, intro-mailen, opbevaringen af adressen og samtykket, og hvor længe en spærring gemmes.
