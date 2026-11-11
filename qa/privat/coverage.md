# Privat – hvad er reelt, halvt bygget eller simuleret (fase 1, prefix PC)

Grundlag: kodegennemgang af `app/modules/privat/**`, `web/src/components/privat/**`, `web/src/lib/privat/**` og
`tests/qa/qa_privat_stack.py` (branch qa/privat-deep). Scenarierne ligger i `qa/privat/scenarios.csv`.

## 1. Simuleret – test aldrig som om det er rigtigt

| Hvad | Hvor | Konsekvens for test |
|---|---|---|
| Web-simulering `fake.ts` (in-browser API) | `web/src/lib/privat/fake.ts:1-11`, `public.tsx:43-50`, `api.ts:566-571` | Bruges ved `NEXT_PUBLIC_PRIVAT_FAKE=1`, for anonyme besøgende (demo) og **stille som fallback**, når API'et svarer 404 / `privat_not_enabled` / `feature_disabled`. Assert altid, at testen rammer :8400 (netværkskald), ellers tester man fake'en. SMS-kode `123456`, simulerede opkaldsudfald, «simulateMember», `?portal=simuleret` findes kun her (PC-SEC-03). |
| AI-model `AI_PROVIDER=fake` | `app/modules/privat/fake.py` | Regex-mapping af prototype-formuleringer til tool-kald. Brug eksempelsætningerne fra Butikken (`example`) – andre formuleringer kan give «forstår ikke» uden at være en produktfejl. |
| Stripe | `tests/qa/qa_privat_stack.py:15-22` | Fake-hosted checkout `/__qa/stripe/pay/<id>`, testkort 4242/3155/0002/9995, `GET /__qa/stripe/sessions`. Billing Portal er ikke en rigtig portal – plan-skift/opsigelse testes ved at poste subscription-objekter. |
| Vapi-opkald | `qa_privat_stack.py`, `calls.py` | Intet ringes; `GET/DELETE /__qa/calls` viser hvad der ville være ringet. Poolnummer `+4589870000`. |
| SMS (telefonverifikation, gruppe-join-kode) | `phone.py:33`, `groups.py:408-420` | Kun `sms.simulated`-linjer i `/home/claude/pd-api.log`. Invitationer sendes slet ikke af Dialogbot (sms:-link fra brugerens egen telefon) – assert at der INGEN sms-række opstår. |
| E-mail | `EMAIL_ADAPTER=simulated` | Assert på outbox/e-mail-rækker. |
| Sponsorindslag | `router.py:269-275` («Pilot: simulated») | Aktiverer kladder gratis (F-PQ-03). |
| Virksomhedssøgning uden Google-nøgle | `places.py` (DemoPlaces) | Demo-virksomheder kan ikke ringes til (409 `demo_business`). Opkaldstests skal bruge et nummer, brugeren selv skriver. |
| Kalender OAuth | `appointments.py:387-410`, `CONNECTORS_PROVIDER=fake` | Fake OAuth-state; ingen rigtig Google/Microsoft. iCal-feed er reelt. |
| Filer (kvitteringer, ønskebilleder) | `files.py`, `wishes_router.py:253` | Lokal mappe + `/privat/dev-files` i stedet for Supabase Storage. |

## 2. «Kommer snart» i QA-stakken (mangler nøgler)

| App | Krav | Status i stakken |
|---|---|---|
| Pakker (`pakker`) | `track17_api_key` | `coming_soon` – enable 409; kun «Giv mig besked» kan testes |
| Rejser (`rejser`) | `duffel_access_token` eller `travelpayouts_token` + marker | `coming_soon` – samme |
| Push | VAPID-nøgler | `/push/*` svarer 501 `push_not_configured`; påmindelser går til e-mail-fallback |
| Produktsøgning (ønsker) | web search | 503 `search_unavailable` |

## 3. Halvt bygget / huller fundet i koden (kandidater til fund – verificér før indberetning)

1. **Plus-apps forbliver brugbare efter plan-udløb.** `addons.require()` tjekker kun «slået til», ikke plan (`addons.py:9-10,808`). Start trial → slå alle til → opsig → alt virker stadig, inkl. påmindelser. Needs-decision (PC-ENT-02/03). F-P2-06 dækker kun re-enable-409.
2. **Ingen sletning af konto/data (GDPR) og ingen eksport** i Privat – hverken endpoint eller UI (PC-ACC-02/03).
3. **Familie «Op til 5 personer»** – intet husstands-endpoint fundet; `people_limit` bruges kun som tal (PC-ENT-08).
4. **Dobbelt abonnement:** `checkout()` blokerer ikke en aktiv kunde (PC-SUB-07).
5. **Planlagte opkald** (`privat.call_due`) gentjekker ikke addon/plan/telefon før der ringes (`calls.py:729-747`, PC-CALL-06).
6. **Garanti:** tilladelsesteksten siger «Gemmer ikke billeder af kvitteringer», men der er et foto-endpoint, som gemmer dem (PC-APP-01).
7. **Rejser** gemmer søgninger i appdata, men er markeret ikke-sletbar (`app_status.py:87`, PC-ACC-05).
8. **PlanSheet** sender altid `interval: "month"` – ingen årsvalg fra Butikken (`apps.tsx:475`, PC-SUB-16).
9. **App-sider uden panel:** kun 8 apps i `PANELS` + 9 husstandsapps i `HOUSEHOLD_APPS`; ring-for-mig, delte-lister, oenskelister og pakkeliste har ingen indstillingsflade (PC-APP-14).
10. **Mine apps-statuslinje** mangler for pakker og rejser (`app_status.py` READERS).
11. **Statisk katalog i web** (`addons-catalog.json`, 21 apps) skal holdes i sync manuelt med backend (PC-SHOP-02).
12. **`/wishes/images`** har hverken addon-krav eller rate limit (PC-WISH-11).
13. **theme-color** `#E0521A` i `web/src/app/privat/layout.tsx:7` vs brand `#C4461A`.
14. Backend-tekster (app-katalog, fejlbeskeder, SMS-forslag, chat) er kun danske – Privat-UI findes på 8 sprog.

## 4. Katalogets 21 apps (addons.py)

| Nøgle | Plan | Kræver | Sletbar data | Panel i web | Reelt i stakken |
|---|---|---|---|---|---|
| ring-for-mig | Basis/Plus/Familie | – | nej | nej | ja (fake Vapi) |
| delte-lister | gratis | – | nej | nej | ja |
| oenskelister | gratis | – | nej | nej (ønske-UI i opgaver) | ja (søgning 503) |
| kalender | Plus/Familie | – | nej | ja | iCal ja, OAuth fake |
| pakker | Plus/Familie | 17TRACK | ja | ja | coming_soon |
| foedselsdage | Plus/Familie | – | ja | ja | ja |
| madplan | Plus/Familie | – | ja | ja | ja |
| bil-og-syn | Plus/Familie | ring-for-mig | ja | ja | ja |
| regninger | Plus/Familie | – | ja | ja | ja |
| laege-og-tandlaege | Plus/Familie | ring-for-mig | ja | ja | ja |
| pakkeliste | Plus/Familie | – | ja | nej | ja |
| rejser | Plus/Familie | Duffel/Travelpayouts | nej | ja | coming_soon |
| abonnementer | Plus/Familie | ring-for-mig | ja | husstand | ja |
| haandvaerker | Plus/Familie | ring-for-mig | ja | husstand | ja (demo-firmaer kan ikke ringes) |
| faelles-udgifter | gratis | – | ja | husstand | ja |
| garanti | Plus/Familie | – | ja | husstand (+foto) | ja (lokale filer) |
| fest | gratis | – | ja | husstand | ja |
| flytning | Plus/Familie | – | ja | husstand | ja |
| kaeledyr | Plus/Familie | ring-for-mig | ja | husstand | ja |
| hus-og-vedligehold | Plus/Familie | – | ja | husstand | ja |
| fitness-og-sundhed | Plus/Familie | – | ja | husstand | ja |

## 5. Praktisk

- Persona «teenager» = angriber med egen konto, der vil have Plus gratis (gen-trial, selvhenvisning, sponsor, apps efter opsigelse).
- Brug unik `x-real-ip` pr. test (funnel og offentlige invitationsopslag er IP-begrænsede).
- Kendte fund, der IKKE må dubleres: F-PQ-01..03, F-P2-01..06, F-BQ-002..006 – scenarierne nævner dem som «regression».
