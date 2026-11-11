# Dialogbot Privat – API-kontrakt (fælles for backend og web)

Alle under /api/v1/privat (web-proxy: /api/backend/privat/...). Kræver login. Arbejder på brugerens PRIVATE arbejdsrum
(workspaces.kind='personal'); oprettes idempotent af POST /privat/account. Fejl følger repoets ApiError-format.
Beløb i credits er heltal. Tider ISO 8601 med tidszone; visning Europe/Copenhagen.

## Typer
Task = {
  id, kind: "list"|"reminder"|"call", title, status: "awaiting_user"|"draft"|"planned"|"in_progress"|"awaiting_business"|"done"|"declined",
  next_step, due_at|null, who, usage_text, is_example: bool, created_at,
  items: [{id, text, done}],                      // lister
  remind_at|null,                                 // påmindelser
  call: null | {business_name, address, phone_display, may_ask, may_agree, may_not, window, max_credits: 3,
                share_phone: bool, result: null|"answered"|"no_answer"|"failed"|"declined",
                confirmed_text|null, business_reply|null, business_price_text|null, duration_seconds|null},
  events: [{at, text}]                            // historik, nyeste sidst
}
Balance = {free_used, free_limit: 10, credits, reserved, sponsor_left_today, phone_display|null, phone_verified: bool,
  plan: "none"|"basis"|"plus"|"familie", plan_status: "trial"|"active"|"past_due"|"canceled"|"expired"|"none",
  trial_days_left: int, calls_quota: int, calls_used: int, calls_left: int, entitled: bool}   // se «Abonnement»
ChatMessage = {id, role: "user"|"assistant", kind: "text"|"task"|"move"|"clarify"|"call_proposal"|"draft"|"waiting"|"booking_proposal",
  // «draft» = en opgave gemt som kladde (kortet åbner betalingsarket). «booking_proposal» = en booking på en virksomheds
  // hjemmeside, der venter på dit ja (Godkend/Afvis, før/efter udfyldt). Egen type, så de aldrig forveksles. Se «Booking på hjemmeside».
  text, task_id|null, about_task_id|null, before|null, after|null,
  options: [{id, label, sub}]|null, links: [task_id]|null, created_at}

## Endepunkter
POST /privat/account                          → {workspace_id, created: bool}
GET  /privat/me                               → Balance
GET  /privat/day                              → {awaiting: Task[], today: Task[], soon: Task[]}
GET  /privat/tasks?status=                    → Task[]
GET  /privat/tasks/{id}                       → Task
POST /privat/tasks/{id}/items/{item_id}/toggle → Task
POST /privat/tasks/{id}/activate {method:"credit"|"sponsor"} → Task   (draft → aktiv; 409 hvis ingen credits / sponsorgrænse)
GET  /privat/messages?task_id=                → ChatMessage[]
POST /privat/messages {text, about_task_id?}  (Idempotency-Key header) → {messages: ChatMessage[], balance: Balance}
POST /privat/messages/{id}/options/{option_id} → {messages: ChatMessage[], balance: Balance}   // svar på clarify
POST /privat/calls/{task_id}/approve {window, share_phone} (Idempotency-Key) → Task   // 409 needs_plan (uden plan/prøveperiode: ingen credits-vej; extra.cta → /privat/konto) | needs_phone | insufficient_credits (kun ekstra opkald, når planens opkald er brugt) | outside_hours
POST /privat/calls/{task_id}/decline          → Task
POST /privat/calls/{task_id}/retry            → Task (tilbage til awaiting_user med nyt forslag)   // 409 needs_plan uden plan
POST /privat/phone/start {phone}              → {sent: true}          // SMS-kode, 6 cifre, 10 min
POST /privat/phone/verify {code}              → Balance
POST /privat/credits/checkout {locale?}       → {url}                 // Stripe Checkout mode=payment, 10 credits («ekstra opkald»), 29,00 kr. inkl. moms (eller valutaens pris)
GET  /privat/subscription                     → Subscription          // ?session_id=cs_… synkroniserer først fra Stripe Checkout-sessionen; ?currency=DKK|SEK|NOK|EUR (en kunde beholder sin)
POST /privat/subscription/checkout {plan, interval, code?, locale?} → {url}  // Stripe Checkout mode=subscription; locale: da|en|de|es|fr|it|no|sv (docs/markets.md)
POST /privat/subscription/portal              → {url}                 // Stripe Billing Portal; 501 not_configured uden Stripe/kunde
GET  /privat/ledger                           → [{id, kind, amount, text, created_at}]
POST /privat/sponsor/claim {task_id}          → Task                  // pilot: simuleret indslag, max 2/dag

## Abonnement (Dialogbot Privat: prøveperiode, Basis, Plus, Familie)
Abonnementet afløser credits som primær model; credits bliver «ekstra opkald». Backend: `app/modules/privat/subscriptions.py`,
tabel `private_subscriptions` (én række pr. privat arbejdsrum). Priser: `app/modules/billing/prices.py` (`PRIVAT_PLANS`, øre inkl. moms) og docs/pricing.md.

- **Prøveperiode:** 14 dage fra oprettelsen af kontoen, uden kort, med Plus-rettigheder (`status:"trial"`, `plan:"plus"`). Konti fra
  før abonnementer fandtes får prøveperioden ved første læsning (fra «nu»). Udløbet → `status:"expired"`, `plan:"none"`, `entitled:false`.
- **entitled** = trial, active eller past_due (og canceled indtil `current_period_end`). Med rettigheder: lister/påmindelser ubegrænsede
  (`Task.paid_by:"plan"`, `usage_text` «Med i prøveperioden» / «Med i Plus»; tæller ALDRIG på de 10 gratis), opkald trækkes af planens
  månedskvote, apps med `included_in` kan slås til. Uden rettigheder: præcis den gamle adfærd (10 gratis opgaver/md., credits til opkald).
- **Opkald:** kvote pr. kalendermåned (Europe/Copenhagen) = `calls_quota`; `calls_used` = godkendte plan-opkald i måneden, hvor resultatet
  ikke er no_answer/failed (et opkald, ingen tager, tæller ikke). `approve`: er der kvote → `private_calls.paid_via:"plan"`, ingen credits
  reserveres, `usage_text` «Opkald N af M i Plus», besvaret → «Opkald N af M i Plus · besvaret, 2 min. 10 sek.». Kvote brugt (eller ingen
  rettigheder) → den gamle credit-sti (3 credits, `paid_via:"credits"`); 409 `insufficient_credits` får `extra {credits, needed,
  calls_left, needs_plan}` (`needs_plan:true` = ingen plan/udløbet trial). Forslagets `usage_text`: «Opkald N af M i Plus, når du godkender»
  eller «Højst 3 credits, når du godkender».
- **Stripe:** Checkout `mode=subscription`, `line_items[0].price_data` {currency dkk, unit_amount (md.-pris eller årstotal), tax_behavior
  inclusive, recurring {interval}}, `product_data.name` «Dialogbot Privat – Plus», metadata {kind:"privat_subscription", workspace_id, plan,
  interval} på sessionen og `subscription_data.metadata`; > 48 timer tilbage af prøveperioden → `subscription_data.trial_end` = trial_ends_at.
  success_url `/privat/konto?abonnement=ok&session_id={CHECKOUT_SESSION_ID}`, cancel_url `/privat/konto?abonnement=annulleret`.
  Valgfri faste price-id'er: `PRIVAT_STRIPE_PRICE_<PLAN>_<INTERVAL>` (fx `PRIVAT_STRIPE_PRICE_PLUS_MONTH`); ellers inline price_data.
  Webhook (`/webhooks/stripe`, samme WebhookEvent-idempotens som credits): `checkout.session.completed` med mode=subscription (henter
  GET /v1/subscriptions/{id}) og `customer.subscription.created|updated|deleted` → upsert. Stripe-status trialing/active → `active`,
  past_due/incomplete/paused → `past_due`, canceled/unpaid/incomplete_expired → `canceled`. Et ældre abonnement, der ender, rører ikke det,
  der afløste det. `GET /privat/subscription?session_id=` læser sessionen FRA Stripe (aldrig fra browseren) og kræver, at den hører til
  kaldernes eget arbejdsrum (404 `session_not_yours`; 422 ved ugyldigt id). Opsigelse/skift: Billing Portal (`POST /subscription/portal`,
  return_url `/privat/konto`).

```
Subscription = {
  plan: "none"|"basis"|"plus"|"familie",
  status: "trial"|"active"|"past_due"|"canceled"|"expired"|"none",   // trial = lokal prøveperiode (Plus-rettigheder)
  interval: "month"|"year"|null,
  trial_ends_at: iso|null, trial_days_left: int,                      // dage tilbage, rundet op (dag 1 = 14)
  current_period_end: iso|null, cancel_at_period_end: bool,
  entitled: bool,
  calls_quota: int, calls_used: int, calls_left: int,                 // denne kalendermåned
  people_limit: int, apps_included: bool,
  currency: "DKK"|"SEK"|"NOK"|"EUR"                                   // rækkens valuta, ellers ?currency=, ellers DKK
  plans: Plan[]                                                       // kataloget i `currency` (frontend hardcoder ingen priser)
}
Plan = {key, name, currency, monthly_minor, yearly_monthly_minor, yearly_total_minor, calls, people, apps_included, recommended: bool, features: string[]}
POST /privat/subscription/checkout {plan: "basis"|"plus"|"familie", interval: "month"|"year"} → {url}   (422 ved ukendt plan)
```
Fejlkoder: 409 `needs_plan` (add-on kræver plan; `extra {addon, plans}`), 501 `not_configured` (portal uden Stripe eller uden kunde),
404 `session_not_yours`. `insufficient_credits` bevares som fallback for opkald.

## Tilføjelse: delte lister (ønskelister, indkøbslister, to-do)
Lister kan deles med andre. To slags deling:
- "group": alle medlemmer kan tilføje og krydse af (fx fælles indkøbsliste). Viser hvem der tilføjede/krydsede af.
- "wishlist": ejeren ser listen, men ALDRIG hvem/om nogen har reserveret ("Jeg køber den") – overraskelsen holdes. Andre medlemmer ser
  reservationer (så to ikke køber det samme), men ikke hvem andre har reserveret, kun "Reserveret".
Roller: owner | editor | viewer. Deling, tilføjelser og afkrydsning fra andre koster ingen gratis opgaver eller credits; listen tæller som
én opgave hos ejeren. Adgang til en delt opgave sker KUN via medlemskab (private_task_members) – aldrig via arbejdsrum-id – og alle
privat-endepunkter skal tjekke det. Invitation via link (token, kan tilbagekaldes, udløber efter 30 dage) eller via e-mail/telefon;
modtageren skal logge ind (privat konto oprettes automatisk ved accept). Ændringer synkroniseres ved polling (GET hver 5. s når siden er synlig)
– intet websocket-krav.

Task får nye felter: list_type: "shopping"|"wishlist"|"todo"|null, shared: bool, share_mode: "group"|"wishlist"|null,
my_role: "owner"|"editor"|"viewer", members: [{id, name, role, is_me}], updated_at;
items[] får: added_by_name|null, done_by_name|null, reserved: bool|null (null for ejeren af en ønskeliste), reserved_by_me: bool, note|null, link|null.

POST   /privat/tasks/{id}/items {text, note?, link?}            → Task   (medlemmer med editor/owner; owner af ønskeliste tilføjer ønsker)
DELETE /privat/tasks/{id}/items/{item_id}                       → Task
POST   /privat/tasks/{id}/items/{item_id}/reserve | /unreserve  → Task   (kun ikke-ejere af en wishlist)
POST   /privat/tasks/{id}/share {mode:"group"|"wishlist", role:"editor"|"viewer"} → {invite_url, token, expires_at}
POST   /privat/tasks/{id}/share/revoke                          → Task   (alle invitationslinks ugyldige)
GET    /privat/invites/{token}       (uden login)               → {title, owner_first_name, list_type, item_count, share_mode}
POST   /privat/invites/{token}/accept                           → Task
GET    /privat/tasks/{id}/members                               → [{id, name, role, is_me}]
DELETE /privat/tasks/{id}/members/{member_id}                   → Task   (owner fjerner; et medlem kan forlade sig selv)
GET    /privat/tasks?shared=1                                   → Task[] (delt med mig + mine delte)
Chat-værktøjer: create_list(type=wishlist|shopping|todo), share_list ("Del indkøbslisten med Anna" → foreslår invitationslink, intet sendes uden ja),
add_items virker også på delte lister man er editor på.

## Tilføjelse 2: Tilføjelser (add-on-butik)
Funktioner ud over kernen leveres som tilføjelser, som brugeren selv slår til/fra i «Tilføjelser». Kernen (altid med): samtale, Min dag,
private lister og påmindelser, kvote/credits/konto. Tilføjelser i første version:
- "ring-for-mig"  Ring for mig – opkald til virksomheder (credits pr. opkald)        status: available
- "delte-lister"  Delte lister – fælles lister, alle kan tilføje                       status: available, gratis
- "oenskelister"  Ønskelister – del ønsker, andre reserverer i hemmelighed            status: available, gratis
- "kalender"      Kalender – læg aftaler i din Google/Outlook-kalender                 status: coming_soon, Plus/Familie
- "pakker"        Pakker – følg dine forsendelser                                       status: coming_soon, Plus/Familie
- "foedselsdage"  Fødselsdage · "madplan" Madplan · "bil-og-syn" Bil & syn · "regninger" Regninger ·
  "laege-og-tandlaege" Læge & tandlæge · "pakkeliste" Pakkeliste                       status: coming_soon, Plus/Familie
  (ikoner: cake, utensils, car, receipt, heart, suitcase – web falder tilbage på «puzzle», indtil de er tegnet)
"ring-for-mig" har included_in = basis/plus/familie (opkald er planens kvote; slået til bliver den ved, og uden plan bruges credits).
Nye tilføjelser skal kunne tilføjes ved at registrere ÉT objekt i et katalog (backend: app/modules/privat/addons.py; web: læser kataloget
fra API) – ingen ændringer spredt rundt i koden.

Addon = {key, name, tagline, description, icon, category, price_text, pricing: "free"|"credits"|"monthly", monthly_price_minor|null,
  status: "available"|"beta"|"coming_soon", permissions: [string] (fx "Ringer til virksomheder du godkender", "Deler en liste via link"),
  requires: [key], enabled: bool, enabled_at|null,
  what: string,            // hvad den gør, 1–2 sætninger (Butikkens bundark)
  example: string,         // hvad man siger til Peter, fx «Ring til cykelværkstedet …»
  steps: [string],         // opsætningstrin, vist før «Start opsætningen» (= enable)
  included_in: [plan key], // tom = gratis for alle; fx ["plus","familie"]
  included: bool,          // kan slås til med mine nuværende rettigheder (trial = Plus)
  requires_plan: bool}     // = included_in ikke tom
GET    /privat/addons                    → Addon[]   (katalog + om det er slået til for mig)
POST   /privat/addons/{key}/enable       → Addon     (409 coming_soon; 409 needs_plan {addon, plans} når included_in ikke dækkes; idempotent)
POST   /privat/addons/{key}/disable      → Addon     (data bevares; delte lister jeg ejer bliver ikke slettet, men deling pauses)
Gating: endepunkter og chat-værktøjer for en tilføjelse kræver at den er slået til (403 addon_disabled {addon:key}). Chatten får kun de
værktøjer, hvis tilføjelser er slået til; beder brugeren om noget fra en slået-fra tilføjelse, svarer den med et kort «Slå <navn> til» (kind:"addon",
addon_key) i stedet for at gøre det. Inviterede medlemmer af en delt liste kan altid se/bruge den liste, de er inviteret til, selv om de ikke selv
har tilføjelsen. Nye konti: "ring-for-mig", "delte-lister" og "oenskelister" slået til som standard i piloten (konfigurerbart PRIVAT_DEFAULT_ADDONS).
ChatMessage.kind får "addon" og feltet addon_key.

## Tilføjelse 3: Invitationer som markedsføring (indbygget vækst)
Al deling går gennem ÉN generisk invitationsmekanisme, som enhver tilføjelse kan bruge (addon.shareable = true + en resource_type),
så fremtidige tilføjelser automatisk får samme invitation, landingsside og belønning.
- private_invites (token, resource_type, resource_id, inviter_user_id, mode, role, created_at, expires_at, revoked_at, opened_count,
  accepted_count) og private_referrals (inviter_user_id, invitee_user_id UNIQUE, invite_token, accepted_at, activated_at, rewarded_at).
- Invitationssiden /privat/invitation/[token] er samtidig reklame: værdien først (listen/ønskerne), derefter et roligt Dialogbot-kort:
  «<Fornavn> bruger Dialogbot – en personlig assistent, der laver lister, minder dig om ting og ringer for dig. Få din egen: 10 gratis
  opgaver hver måned». Ingen pop-ups før personen har set listen.
- Ved accept: oprettes privat konto (hvis ingen), personen lander direkte i den delte liste med et lille banner «Prøv selv: Hvad skal jeg
  klare for dig?». Kilde gemmes (signup_source = invite:<token>).
- Belønning: når en inviteret NY bruger er aktiveret (bekræftet e-mail + har oprettet sin første EGNE opgave), får både inviter og
  inviteret +3 credits (ledger kind "referral", source_ref referral:<invitee_user_id>:inviter / :invitee – unikke, så det sker én gang pr.
  person i hele levetiden). Højst 10 belønninger pr. inviter pr. måned. Eksisterende brugere giver ingen belønning.
- Delingstekst (navigator.share/kopi) foreslås på dansk med Dialogbot-navnet: «Mette har delt sin ønskeliste med dig via Dialogbot:
  <link>». Open Graph-billede for invitationslinks: listens titel + fornavn + Dialogbot-mærket – ALDRIG ønsker/varer (privatliv).
- Delte visninger har en diskret fod «Delt via Dialogbot · Lav din egen liste» (link til /privat?ref=<token>).
- Lov: Dialogbot sender IKKE markedsføring til inviterede. Invitationer deles af brugeren selv via egne kanaler (share-ark/kopi). Hvis vi
  senere sender en invitation pr. e-mail for brugeren, er den ren service (kun invitationen, brugerens navn, ingen tilbud). Ingen nyhedsbrev-
  tilmelding uden aktivt samtykke (markedsføringsloven § 10).
Endepunkter:
GET  /privat/invites/{token}                 (offentlig) → + {inviter_first_name, resource_type, addon_key, cta_text}
GET  /privat/referrals                       → {invited, joined, activated, credits_earned, monthly_left}
GET  /privat/og/invite/{token}.png           (offentlig) → OG-billede (eller i web: Next opengraph-image for invitationsruten)
GET  /operator/privat/growth                 (kun operatører) → {invites_created, opened, accepted, new_users_from_invites, activated, k_factor,
                                                 by_addon:{key:{...}}}
Konto-siden viser «Inviter venner» med optjente credits og et delelink til Dialogbot generelt (/privat?ref=<user-token>).

## Tilføjelse 4: Grupper («Mine folk») – del med mange på én gang
Brugeren gemmer grupper i Dialogbot (Familien, Fodboldforældrene, Kollegerne). Deling med en gruppe = ét tryk.
- private_groups (id, owner_user_id, name, created_at) og private_group_members (id, group_id, name, phone_e164|null, user_id|null,
  joined_via_invite_id|null). Kun ejeren ser gruppen. Numrene bruges KUN til at brugeren selv kan sende fra sin egen telefon – et tastet
  nummer slås ALDRIG op mod Dialogbots brugere (F-P2-02-X10: ville afsløre om/hvem nummeret er og melde fremmede ind uden
  samtykke) – vi kontakter dem aldrig selv, ingen markedsføring, slettes med gruppen/kontoen.
- Smart opbygning: (1) «Folk du har delt med» – personer der har accepteret brugerens invitationer foreslås automatisk (med navn);
  (2) vælg fra kontakter (Android Contact Picker) – kun de valgte gemmes, efter et klart «Gem i gruppen»; (3) skriv navn + nummer;
  (4) indsæt flere numre på én gang (komma/linjeskift, normaliseres til +45); (5) i chatten: «Del ønskelisten med familien»
  → bruger gruppen; findes den ikke: «Skal jeg lave gruppen Familien med Anna, Peter og Mor?» (forslag, kræver ja).
- Når der deles med en gruppe:
  * medlemmer med kendt user_id – dvs. personer der SELV har sagt ja til brugeren før (accepteret en invitation → «Folk du har delt
    med», et personligt link fra gruppen, eller gruppe-linket) – tilføjes DIREKTE til listen og får besked i appen (+ push) – ingen SMS;
    `has_dialogbot` er kun sand for dem;
  * resten får SMS fra brugerens EGEN telefon: Dialogbot forbereder det hele. To valg:
    - «Én samlet SMS» (gruppebesked): sms-link med alle numre + tekst – ét tryk på Send. Ét fælles link.
    - «En ad gangen» (anbefalet når man vil se hvem der er med): en kø med en personlig tekst + personligt kort-link pr. person
      («Hej Anna! …»); Dialogbot åbner SMS-appen for næste person, og brugeren trykker Send; «Næste: Peter (2 af 5)».
  * Bagefter viser listen pr. person: «Med» / «Inviteret» / «Ikke åbnet endnu» (via personlige links), og «Påmind» åbner en ny SMS
    fra egen telefon.
Endepunkter:
GET/POST /privat/groups ; PATCH/DELETE /privat/groups/{id}
POST   /privat/groups/{id}/members  {members:[{name, phone}]}  (normaliserer, dropper dubletter)  ; DELETE /privat/groups/{id}/members/{mid}
GET    /privat/people/suggested      → personer der har accepteret mine invitationer (navn, har Dialogbot)
POST   /privat/tasks/{id}/share-group {group_id, mode, role, style:"group_sms"|"one_by_one"}
       → {added_in_app:[{name}], sms_group:{recipients:[e164], body, short_url}|null,
          sms_queue:[{member_id, name, phone_e164, body, short_url}]|null}
GET    /privat/tasks/{id}/invite-status → [{name, status:"member"|"opened"|"invited"}]

## Tilføjelse 5: Kontakter fra iPhone
Safari på iPhone kan ikke læse kontakter. Tre veje, alle i piloten:
1. Gruppe-link («Byg gruppen selv»): brugeren sender ÉT link til en eksisterende gruppechat (iMessage/SMS/WhatsApp/Messenger) fra sin
   egen telefon: «Tryk her for at komme med i Familien på Dialogbot». Hver der trykker, skriver navn (og evt. nummer med SMS-kode) eller
   logger ind, og lander i gruppen. Brugeren ser dem dukke op. Ingen kontakter importeres.
   POST /privat/groups/{id}/join-link → {short_url, short_code, suggested_text, expires_at} ; POST /privat/groups/{id}/join-link/revoke
   GET  /privat/group-invites/by-code/{code} (offentlig) → {group_name, owner_first_name, member_count}
   POST /privat/group-invites/by-code/{code}/join {name, phone?} → {joined:true}   (login valgfrit; uden login gemmes navn + evt. verificeret nummer)
2. vCard-import (.vcf): iPhone → Kontakter → hold fingeren på en liste (iOS 16+) → «Eksportér» eller del én kontakt → «Gem i Filer»;
   i Dialogbot «Importér fra fil» (input accept=".vcf,text/vcard,text/x-vcard"). Filen læses i browseren (vCard 2.1/3.0/4.0: FN, N, TEL,
   flere numre → vælg mobil), brugeren vælger personer, og KUN de valgte sendes til POST /privat/groups/{id}/members. Filen uploades aldrig.
3. Indsæt numre (findes allerede).
Senere (fase 2): en tynd iOS/Android-app (Capacitor) med den rigtige kontaktvælger (CNContactPickerViewController – ingen adgang til
hele adressebogen) og den native SMS-skærm (MFMessageComposeViewController, flere modtagere, ved om beskeden blev sendt) + push.

## Tilføjelse 6: Find virksomheden selv + push-notifikationer (skal virke i piloten)
### Find virksomheden
Assistenten slår selv virksomheden op, når brugeren skriver «Ring til cykelværkstedet …» eller «Ring til Fona i Bruuns Galleri».
Kilde: Google Places API (New) via den eksisterende klient app/modules/sales/places.py (Text Search med Pro-felter, derefter Place Details
for nationalPhoneNumber/internationalPhoneNumber, regularOpeningHours, rating, userRatingCount – kun for de 3 viste kandidater).
Uden GOOGLE_PLACES_API_KEY: DemoPlaces (fiktive, kan aldrig ringes op). Placering: brugerens profil (postnummer/by) eller browserens
position, som der KUN spørges om, når en søgning har brug for den; ellers spørger chatten «Hvilken by?». Resultater må ikke caches ud over
Googles regler (place_id må gemmes; øvrigt indhold højst GOOGLE_PLACES_CACHE_DAYS). Vis «Data fra Google» ved resultater (krav).
Åbningstider bruges: er virksomheden lukket nu, foreslår assistenten næste åbningstid og planlægger opkaldet dér (status planned).
Ingen nummer fra Google → assistenten siger det og beder om nummeret. Kun numre der ser ud som rigtige danske erhvervsnumre (+45, 8 cifre)
kan ringes op; mobilnumre (2x/3x/4x/5x/6x/7x/8x/9x – brug sales.service.danish_number-reglerne) kræver at brugeren bekræfter «Det er en virksomhed».
GET  /privat/businesses/search?q=&lat=&lng=&city=  → [{place_id, name, address, phone_display, phone_e164|null, rating|null,
      rating_count|null, open_now|null, next_open_text|null, distance_km|null, maps_url, source:"google"|"demo"}]  (max 3; rate-limit pr. bruger 30/time)
Chat-svaret «clarify» får options fra denne søgning (sub = adresse · afstand · åben/lukket · ★).
PATCH /privat/me/location {city?|postcode?|lat,lng}  (gemmes kun når brugeren selv giver den)

### Push-notifikationer (Web Push, VAPID)
Påmindelser, svar fra virksomheder, opkaldsudfald, nye medlemmer/tilføjelser på delte lister og invitationer der er accepteret sendes
som push. E-mail bruges kun som reserve, hvis brugeren ingen aktive push-abonnementer har, eller push fejler (410 Gone → slet abonnement).
- service worker web/public/sw.js (push + notificationclick → åbner den relevante side), registreres fra /privat.
- Tabel push_subscriptions (id, user_id, endpoint UNIQUE, p256dh, auth, user_agent, created_at, last_success_at, failures).
- Afsendelse via pywebpush (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT=mailto:...) i en outbox-handler push.send (retries/backoff).
- iPhone: virker fra iOS 16.4, når siden er føjet til hjemmeskærmen. Web viser en kort vejledning («Del → Føj til hjemmeskærm») før
  der spørges om tilladelse, og kun når brugeren laver sin første påmindelse eller godkender et opkald.
GET    /privat/push/public-key → {public_key}
POST   /privat/push/subscriptions {endpoint, keys:{p256dh, auth}} → {id}
DELETE /privat/push/subscriptions {endpoint}
POST   /privat/push/test → {sent: n}   (sender «Det virker – du får besked her»)
GET    /privat/me får: push_enabled: bool, location_city|null

---

# Implementering (backend, app/modules/privat) – afvigelser og præciseringer

Alt ovenfor er implementeret. Afvigelser er bagudkompatible (kun ekstra felter/endepunkter) og står her.

## Generelt
- Feature-flag: `PRIVAT_ENABLED` (standard false) + `PRIVAT_ALLOWED_EMAILS` (kommaliste; tom = alle). Uden adgang: 403 `privat_not_enabled`.
  Offentlige invitationsendepunkter svarer 404 `invite_invalid`, når flaget er slået fra.
- Privat konto kræver bekræftet e-mail **eller** bekræftet mobilnummer (403 `email_not_verified` når ingen af delene er sat).
  GET-endepunkter uden konto: 404 `privat_account_missing`; POST-endepunkter opretter kontoen automatisk (samme som `POST /privat/account`).
- **Konto via telefon (quiz-funnelen `/privat/start`, docs/funnel-api.md):** ved verify af SMS-koden sættes `users.phone_verified_at`, og
  `deps.ensure_account` accepterer det som bevis i stedet for e-mailen. Kontoen oprettes med en tilfældig adgangskode og en velkomstmail
  med «Vælg adgangskode»-link; e-mailen forbliver uverificeret, til brugeren selv bekræfter den. Profilens `phone_e164`/`phone_verified_at`
  sættes fra funnelen, så `needs_phone` ikke rammer ved det første opkald. Findes e-mailen allerede, åbnes kontoen IKKE:
  `409 account_exists` uden session (audit `funnel.account_exists`; hotfix #177).
- «Se som kunde» (operatør-sessioner) kan ALDRIG se private data: 403 `view_as_not_allowed`.
- Isolation: et privat arbejdsrum (`workspaces.kind='personal'`) kan aldrig nås via `/workspaces/{id}/…` (404), vises ikke i
  `GET /workspaces`, admin-kundelister/-tal, daglige rapporter eller fakturering. Opgaver nås KUN via `private_task_members`.
- Fejlkoder (409 medmindre andet): `needs_phone`, `insufficient_credits`, `outside_hours`, `sponsor_limit`, `coming_soon`, `needs_plan`,
  `already_reserved`, `not_reserved_by_you`, `share_mode_locked`, `call_not_proposed`, `call_running`, `code_expired`,
  `too_many_attempts`, `too_soon`, `demo_business`; 403: `addon_disabled` (+ `addon`), `read_only`, `owner_only`, `use_reserve`,
  `owner_cannot_reserve`, `sharing_paused`; 404 `invite_invalid`; 422 forkert kode (+ `attempts_left`); 429 `rate_limited`;
  501 `calls_not_configured` (mangler Vapi-nøgle eller puljenummer).

## Typer – præciseringer
- `Task.call.may_ask`, `may_agree`, `may_not` er tekststrenge (én sætning hver). `Task.call` har også `status`
  (proposed|approved|dialling|in_progress|unknown|answered|no_answer|failed|declined).
- `Task.events` er tom for medlemmer af en ønskeliste (kun ejer og «group»-lister viser historik). `usage_text` for et medlem er
  «Delt med dig – koster dig ingenting».
- `ChatMessage` har også `answered_option_id` (valgt svar på en clarify) og `addon_key` (kind "addon").
  `options[].id` er stabile id'er; serverens handlingsdata sendes aldrig ud.
- Påmindelsesstatus: planned → done, når påmindelsen er sendt (push; e-mail kun uden aktivt abonnement).

## Regler
- Med prøveperiode eller plan (`entitled`): ubegrænsede lister/påmindelser (`paid_by:"plan"`) og opkald af planens kvote – se «Abonnement».
- Ellers 10 gratis digitale opgaver (lister/påmindelser) pr. kalendermåned (Europe/Copenhagen). Opkald bruger ikke gratis opgaver.
  Opgave nr. 11 → `draft` (en draft-påmindelse sendes aldrig) indtil `activate` (1 credit, `spend:<task_id>`) eller sponsor
  (højst 2 pr. dag, `sponsor:<task_id>`). Rettelser, afkrydsning, læsning, afklaring og alt, som medlemmer gør på en delt liste, er gratis.
- Balance = SUM(credit_ledger). `reserve` −3, `capture` 0 (reservationen bliver forbruget), `release` +3. `reserved` = åbne reservationer.
- Velkomst +3 én gang (`welcome:<workspace_id>`). Køb: +10 (`stripe:<checkout_session_id>`), KUN via Stripe-webhook; webhooken gemmer
  `WebhookEvent(provider='stripe', event_id)` i samme transaktion for ALLE Stripe-hændelser.

## Opkald («Ring for mig»)
- Chatten opretter kun et forslag; der ringes først ved `approve` (låser modtager, nummer, regler, tidsrum, share_phone i
  `approved_snapshot`). Status committes før Vapi kaldes; intet svar fra Vapi = `unknown` (ringes aldrig op igen automatisk).
  Uden rapport i 30 min. frigives reservationen af workerens planlagte job.
- Opkald fra puljenumre i `PRIVAT_POOL_NUMBERS` (fx `+4589871234=<vapi-phone-number-id>`). Samme virksomhed får altid samme puljenummer.
- Virksomhedsopslag: se «Find virksomheden» nedenfor. Et nummer, brugeren selv skriver, skal stå i brugerens egne beskeder
  (modellen kan ikke opfinde det). Det fiktive Aarhus-fixture (Cykelmageren / Østbyens Cykler) bruges kun med FakeProvider i dev/test.
- Tilbageopkald til et puljenummer rutes på opkalderens nummer til nyeste åbne opkald til den virksomhed (14 dage). Flere brugere →
  assistenten spørger hvem; ukendt → høflig generisk besked uden persondata. Viderestilling til brugerens verificerede mobil kun ved share_phone.

## Tilføjelser, invitationer, grupper – præciseringer
- Ekstra: `POST /privat/addons/{key}/invites {resource_id?, mode?, role?}` (generisk invitation for enhver delbar tilføjelse),
  `POST /privat/referrals/link` («Inviter venner»), `POST /privat/invites/by-code/{code}/accept`.
- Del-svar (`/share`, `/addons/{key}/invites`, `/referrals/link`): `{invite_url, token, short_code, short_url, expires_at,
  suggested_text, share_text}` (`share_text` = `suggested_text`). `suggested_text` er dansk, GSM-7, ≤160 tegn, uden emoji.
  Dialogbot sender ALDRIG invitationer selv (ingen SMS/e-mail-endepunkter) og gemmer ingen kontakter.
- `signup_source` gemmes som `invite:<private_invites.id>` (aldrig selve tokenet).
- Belønning: inviteret får +3 også når inviterens månedsgrænse (10) er nået; kun inviteren springes over.
  Ny bruger = kontoen er oprettet efter invitationen; selvinvitation og eksisterende brugere giver intet.
- `k_factor` = new_users_from_invites / antal private konti (i perioden; `?days=` valgfri).
- Slår ejeren `delte-lister`/`oenskelister` fra, pauses delingen: medlemmer får 403 `sharing_paused`, åbne links bliver ugyldige; data bevares.
- `GET /privat/invites/{token}` og `/by-code/{code}` tæller `opened_count`.
- Grupper: kun ejeren kan læse dem (andre får 404). `POST /privat/groups` tager også `members`; `POST /privat/groups/{id}/members`
  tager også `paste` (numre adskilt af komma/linjeskift) og `user_id` (kun personer fra `/people/suggested`); svaret er gruppen +
  `result {added, duplicates, invalid}`. `GET /privat/groups` → grupper med `members[{id, name, phone_e164, phone_display, has_dialogbot}]`.
- Gruppe-link uden login: `join {name, phone}` sender en SMS-kode og svarer `{joined:false, code_sent:true}`; kald igen med
  `{name, phone, code}`. Højst 50 nye medlemmer pr. link pr. time, 20 koder pr. link/time, 3 pr. nummer/time (429 `rate_limited`).
  `join` svarer også `already`.
- Rate limits på de offentlige opslag (`GET /privat/invites/{token}`, `GET /privat/invites/by-code/{code}`,
  `GET /privat/group-invites/by-code/{code}` samt accept/join af links): pr. IP 30/min og 300/døgn; forkerte/ukendte koder
  tælles strengere: 10/min og 50/døgn; desuden højst 1000 forkerte opslag i timen i alt. Over grænsen: 429 `rate_limited`
  («Der er prøvet for mange links fra din forbindelse. Vent lidt, og prøv igen.») – også for gyldige koder. IP = første adresse i
  `X-Forwarded-For` (web-BFF'en skal videresende besøgendes adresse); kun en nøglet hash af IP'en gemmes, rækker slettes efter 2 døgn.
- OG-billede (`/privat/og/invite/{token}.png`) er ikke lavet i backend – web bruger Next opengraph-image (titel + fornavn + mærke, aldrig varer).

## Find virksomheden og push (Tilføjelse 6) – sådan virker API'et
- Søgning: den eksisterende klient `app/modules/sales/places.py` (Text Search med Pro-felter → Place Details kun for de ≤ 3 viste).
  Mangler `GOOGLE_PLACES_API_KEY` i API-tjenesten, logges én advarsel (`privat.places_key_missing`), og DemoPlaces bruges
  (fiktive numre, som aldrig ringes op: 409 `demo_business`). Kun `place_id` gemmes varigt; adresse/åbningstid på forslag og
  valg i chatten ryddes efter `GOOGLE_PLACES_CACHE_DAYS`. Søgninger: 30 pr. bruger pr. time (429 `rate_limited`).
  Søgning med Google uden kendt placering → 409 `needs_location`.
- Chat: mangler placering, svarer chatten med en clarify med options `location:geo` og `location:city` (web spørger, kalder
  `PATCH /privat/me/location` og sender brugerens besked igen). Resultater er clarify-options med id `place:<place_id>`
  (`place:demo…` for DemoPlaces) og `sub` = «adresse · afstand · åben nu/lukket nu · ★ x,x (n) · telefon». Valg via
  `POST /privat/messages/{id}/options/{option_id}` laver ALTID et opkaldsforslag (call_proposal) – der ringes aldrig uden godkendelse.
- Nummerregler: kun numre, som `sales.service.danish_number` accepterer. Uden nummer: forslaget laves med `call.phone_e164 = null`, og
  brugeren svarer med nummeret som almindelig chatbesked med `about_task_id` = opkaldsopgaven; serveren tager nummeret, sætter det på
  forslaget og svarer med en tekst + en ny `call_proposal`. Godkendelse uden nummer → 409 `needs_business_phone`.
  Mobil-lignende nummer: `call.is_mobile = true`, og approve kræver `confirm_business: true` (ellers 409 `confirm_business`).
- `Task.call` har også: `phone_e164`, `is_mobile`, `source` ("google"|"demo"|"user"), `open_now` (null uden åbningstider),
  `next_open_text`, `scheduled_for`.
- Lukket nu: forslaget fortæller næste åbningstid (inden for hverdage 8–18). `approve` uden `at_next_open` → 409 `business_closed`
  (eller `outside_hours`) med `next_open_at`/`next_open_text`; med `at_next_open: true` reserveres 3 credits, opkaldet får status
  `scheduled`, opgaven `planned`, og workeren ringer på tidspunktet (job `privat.call_due`) – kun fordi godkendelsen er gemt.
  Godkender brugeren ikke, minder job `privat.call_ask` om forslaget, når virksomheden åbner (ringer aldrig selv). Et planlagt opkald kan
  annulleres med `decline` (credits frigives).
- Deling i chatten: `kind: "share_proposal"` (task_id = listen). Med en gruppe er `options[0]` = `{id: group_id, label: gruppenavn}`;
  web åbner sit dele-ark. Svar på options-endepunktet med gruppens id deler også (én ad gangen).
- `GET /privat/invites/{token}` accepterer også en kort kode (8 tegn) som token.
- `GET /privat/groups` → medlemmer har også `user_id`.
- Push: `push.send` i outboxen (retry/backoff). 404/410 sletter abonnementet; e-mail sendes, hvis det var det sidste, eller når push
  fejler for sidste gang. Påmindelser, opkaldsudfald, tilbageopkald, «X har åbent nu» og accepterede invitationer: push, ellers e-mail.
  Nye punkter/medlemmer på delte lister: kun push, højst én pr. liste pr. modtager pr. 2 minutter, aldrig til den, der gjorde det, og
  aldrig for reservationer. Uden VAPID-nøgler: `GET /privat/push/public-key` → 501 `push_not_configured`, og alt går som e-mail.

## Nye miljøvariabler
`PRIVAT_ENABLED`, `PRIVAT_ALLOWED_EMAILS`, `PRIVAT_POOL_NUMBERS`, `PRIVAT_STRIPE_PRICE_ID` (valgfri; ellers inline-pris 2900 øre
inkl. moms), `PRIVAT_STRIPE_PRICE_{BASIS,PLUS,FAMILIE}_{MONTH,YEAR}` (valgfri faste Stripe-priser for abonnementerne; ellers inline
price_data), `PRIVAT_DEFAULT_ADDONS` (standard `ring-for-mig,delte-lister,oenskelister`), `PRIVAT_SHORT_URL_BASE`
(standard `https://dialogbot.app/i/`), `PRIVAT_GROUP_URL_BASE` (standard `https://dialogbot.app/g/`).
`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (Web Push; `python -m scripts.generate_vapid` laver et par – læg det aldrig i git).
`GOOGLE_PLACES_API_KEY` (findes allerede) skal også stå på API-tjenesten, ikke kun workeren.


## Booking på hjemmeside (browser-agenten) – Godkend/Afvis og kørslen

Assistenten kan booke på en virksomheds offentlige bookingside (kun godkendte bookingmotorer og domæner; se
`docs/ADR-004-browser-worker.md`). Agenten udfylder bookingen, men **trykker aldrig «Bekræft/Book/Betal/Send» uden dit ja**. Slået
fra, medmindre `BROWSER_WORKER_ENABLED=true`. Kan agenten ikke (CAPTCHA, login, intet ledigt, for mange trin), falder opgaven tilbage til
telefonsporet (`call`).

```
GET  /privat/tasks/{id}/browser          → BrowserRun      // seneste kørsel. 404 hvis opgaven ikke er din, eller der ingen kørsel er
POST /privat/tasks/{id}/browser/approve  (Idempotency-Key) → BrowserRun   // 409 browser_run_not_awaiting | approval_expired
POST /privat/tasks/{id}/browser/decline  (Idempotency-Key) → BrowserRun   // 409 browser_run_not_awaiting
```

```
BrowserRun = {id, task_id, engine, mode: "playbook"|"llm"|null,
  status: "planned"|"running"|"awaiting_approval"|"approved"|"done"|"failed"|"fallback_phone",
  goal: {intent: "book"|"flyt"|"aflys", service, preferred_windows: [{date, from, to}], contact: {name, phone?, mail?}, business_name?},
  before_after: {service, staff, date, time, price, name, ...}|null,        // det udfyldte forslag, før intet er bekræftet
  steps: [{n, tool, arg, result, at, screenshot_url|null}],                   // uden refs/selectors og uden det, der blev skrevet i felter
  evidence: [{kind: "screenshot"|"video"|"receipt_pdf", name, url}],          // url: signeret, udløber efter 5 minutter
  result: {reference?, receipt_text?, summary?, found?}|null, error_code|null,
  max_steps, max_seconds, started_at, awaiting_since, approval_expires_at|null, approved_at, finished_at, created_at}
```

- **Forløb.** Agenten udfylder, stopper ved bekræft-knappen og sender en `ChatMessage` af `kind: "booking_proposal"` med `before`/`after` og
  to valg: `options: [{id:"approve",label:"Godkend"},{id:"decline",label:"Afvis"}]`. Valgene kan besvares enten via
  `POST /privat/messages/{id}/options/{option_id}` (som chatten gør) eller via `…/browser/approve|decline`: det er den samme handling.
  Opgaven står som `awaiting_user`.
- **Godkend** er idempotent (gentagelse = samme tilstand, ingen anden effekt; `Idempotency-Key` genafspiller svaret). Browser-sessionen holdes
  i live i `BROWSER_APPROVAL_TTL_SECONDS` (standard 600). Dit ja gælder **præcis det forslag, du så**: har siden ændret sig, når
  sessionen er udløbet og køres igen, bekræftes intet, og du får et nyt forslag. Et ja ældre end 24 timer afvises (`approval_expired`).
  Udløbet TTL → en **playbook**-kørsel genafspilles til samme punkt; en **LLM**-kørsel kan ikke genafspilles og går til `fallback_phone`
  (`error_code=session_expired`). Når bookingen er gennemført: `done`, opgaven får tid og pris (`next_step`, begivenheder, `call.confirmed_text`)
  og kvitteringen gemmes som PDF + screenshot.
- **Afvis** er idempotent: `failed` med `error_code=declined`, opgaven bliver `declined`, intet er booket.
- **Mulig uønsket booking.** Fører et klik, som ikke så ud som en bekræftelse, til en side, der ligner en kvittering, stopper kørslen
  (`failed`, `error_code=unexpected_commit`). Opgaven bliver `awaiting_user`, og beskeden til dig indeholder siden og teksten:
  *«Bookingen kan være gennemført – ring eller skriv til virksomheden for at aflyse, hvis du ikke ønsker den.»* Samme tekst
  (`commit_unconfirmed`), hvis bekræft blev trykket, men ingen kvittering kunne læses. Der siges aldrig «intet er booket» efter et bekræft-klik.
- **Telefon-fallback.** Kan agenten ikke (CAPTCHA, login, intet ledigt, budget, ukendt side ...), bliver opgaven en `call`-opgave i `awaiting_user`
  med et opkaldsforslag (`call_proposal`), hvor `may_ask` indeholder det, agenten nåede at se (ydelse, ledige tider). Der ringes først, når du
  godkender opkaldet som ethvert andet opkald. `error_code`/`result.found` på kørslen viser årsagen.
- **LLM-fallback.** Er motoren ukendt, eller rammer en playbook-selector ikke, overtager en model med de samme syv værktøjer og de samme hårde
  grænser (`mode: "llm"`). En LLM-kørsel kan ikke genafspilles: er dens session udløbet, går den til telefonen (`session_expired`).
  `unsafe_target`: en tilladt vært pegede på en intern adresse, og kørslen blev afvist, før en browser startede.
- **Evidens** ligger i en privat Supabase-bucket (`BROWSER_EVIDENCE_BUCKET`) og udleveres kun som signerede, kortlivede links.
- **Fejlkoder i `error_code`:** `declined`, `unexpected_commit`, `commit_unconfirmed`, `forbidden_field`, `commit_limit`,
  `approval_expired`, `worker_lost`, `internal_error`; `fallback_phone`: `captcha`, `login_required`, `budget_steps`, `budget_time`,
  `no_availability`, `session_expired`, `unexpected_step`, `playbook:<årsag>`.

### Assistentens bookingværktøjer (tilføjelsen «Ring for mig»)

| Værktøj | Hvad |
|---|---|
| `find_business(name, city?)` | Slår virksomheden op (CVR + Google Places), gemmer opslaget. Svarer med `business_id` og fakta. Opfinder intet |
| `start_booking(business_id, intent, service, preferred_windows[], user_said_track?)` | Vælger spor efter faste regler (se nedenfor), siger hvilket, og starter enten en browser-kørsel eller et opkaldsforslag |
| `switch_to_phone(task_id?)` | «Ring i stedet»: stopper en kørsel, der ikke har trykket bekræft, frigiver creditten og laver opkaldsforslaget |

Sporregler, i rækkefølge (kode i `app/modules/browser/routing.py`; modellen vælger ikke): 1. brugeren sagde «ring» → telefon; «skriv» → browser, hvis det kan lade sig gøre,
ellers telefon med forklaring; 2. ønsket er ikke `book` → telefon; 3. hjemmeside fundet + kendt og tilladt motor + bookingadresse + brugerens navn og bekræftede mobil på profilen
(+ workeren slået til + 1 credit) → browser; 4. ellers telefon. Er ydelse eller tidsramme ikke konkret, spørger assistenten; der startes intet.
En browser-booking koster **1 credit** (reserveres, bruges ved booking, frigives ellers). Kørslen får kun brugerens eget navn og mobilnummer.

## Kalender (tilføjelsen «Kalender»)

Aftaler, brugeren har godkendt, kommer i brugerens egen kalender. Kode: `app/modules/privat/appointments.py`,
`app/modules/privat/calendar_router.py`. Tilføjelsen er med i Plus og Familie (`included_in`), som før.

**Hvornår der bliver en aftale** (tabellen `private_appointments`, én pr. ærinde via `source_ref`):

| Kilde | Hvornår | Tidspunkt |
|---|---|---|
| `call` | Opkaldet er besvaret, og virksomheden bekræftede en tid (`outcome=confirmed`) – også ved et tilbageopkald | Modellens `starts_at` (lokal ISO), hvis den er plausibel; ellers læses `confirmed_text` («torsdag kl. 15.30», «12. november kl. 9») ud fra datoen for opkaldet |
| `browser` | Brugeren sagde ja, og bookingen er bekræftet (`finish_done`) | Sidens dato + tid (`before_after`/`summary`) |
| `manual` | Brugeren fortæller assistenten en tid (`add_to_calendar`) | Den tid, brugeren selv skrev |

Er tidspunktet ikke sikkert (intet klokkeslæt, ingen dag, i fortiden, mere end 400 dage frem), laves **ingen** aftale; opgaven
beholder teksten. Varighed: det virksomheden sagde (`duration_minutes`), ellers 60 minutter. Aftalen gemmes, også når appen er slået
fra; den synkroniseres først, når appen er slået til. Beskeden siger kun «Tiden er lagt i din kalender», når appen er til, og Google/Outlook
er forbundet eller kalenderlinket findes.

**Endpoints** (alle kræver appen slået til → ellers `403 addon_disabled`, undtagen `GET /calendar` og frakobling):

| Metode | Sti | Svar |
|---|---|---|
| GET | `/privat/calendar` | `{enabled, feed: {active, created_at}, providers: {google, microsoft}: {available, connected, status, account_label, error}, appointments: [...]}` |
| POST | `/privat/calendar/feed` | `{url, webcal_url}` – et **nyt** hemmeligt link; det gamle holder op med at virke. Vises kun her, kun en SHA-256 gemmes |
| DELETE | `/privat/calendar/feed` | 204 – linket stopper |
| POST | `/privat/calendar/connect/{google\|microsoft}` | `{url}` – send brugeren dertil. Samme OAuth-klient og callback som erhvervsdelen; callbacken ser det personlige arbejdsrum og sender tilbage til `/privat/kalender?connected=…` (eller `?error=…`) og lægger de kommende aftaler i kø |
| DELETE | `/privat/calendar/connect/{provider}` | 204 – adgangen tilbagekaldes hos udbyderen (bedste forsøg), nøglerne slettes |
| GET | `/privat/appointments` | `{items: [Appointment]}` – kommende, bekræftede |
| GET | `/privat/appointments/{id}.ics` | `text/calendar`-fil («Tilføj til kalender») |
| DELETE | `/privat/appointments/{id}` | Aftalen fjernes fra brugerens kalendere (`status=cancelled`). **Aflyser intet hos virksomheden** |
| GET | `/privat/calendar/feed/{token}.ics` | Offentlig (kalender-apps kan ikke logge ind). 404 ved ukendt token, eller når appen er slået fra. Aftaler fra 60 dage tilbage og frem; aflyste med `STATUS:CANCELLED` |

`Appointment`: `{id, task_id, source, title, location, notes, starts_at, ends_at, status, when_text, ics_path, sync: {<connector>: {synced, error}}}`.
`Task.appointment` (ejer, opkaldsopgaver, appen slået til): `{id, when_text, ics_path}`.

**Synkronisering.** Hver ændring er en outbox-hændelse `privat.calendar_sync` (dedupe pr. aftale og `sequence`), som hovedworkeren
udfører: opret / flyt / slet i hver forbundet kalender. En midlertidig fejl prøves igen; ved sidste forsøg gemmes fejlen på aftalen
(`sync.<connector>.error`), og appen viser den. En udløbet adgang markerer forbindelsen `error`.

**Hemmeligheden i linket.** Tokenet står kun i stien; `app/core/logging.py` erstatter det med `***` i request-loggen, og API'ets
`uvicorn` kører med `--no-access-log`. Renders egen HTTP-log ved kanten kan stadig indeholde stien (ikke styret af os).

**Assistentens værktøjer** (tilføjelsen «Kalender»): `add_to_calendar(title, starts_at, minutes?, location?)` – kun en tid, brugeren selv
skrev; `calendar_status()` – fortæller, hvad der er forbundet, og hvordan man forbinder (Apps → Kalender).

## Fødselsdage (tilføjelsen «Fødselsdage»)

Fødselsdage, brugeren selv fortæller om. Kode: `app/modules/privat/birthdays.py`, endpoints i `app/modules/privat/apps_router.py`.
Med i Plus og Familie. Kun navn, dag og måned gemmes – og året, når brugeren selv siger det (så siges alderen).

| Metode | Sti | Svar |
|---|---|---|
| GET | `/privat/birthdays` | `{items: [Birthday]}` i den rækkefølge, de kommer |
| POST | `/privat/birthdays` | `{name, date, remind_days_before?}` → `Birthday + {created}`. Samme navn (store/små bogstaver ligegyldigt) retter datoen. `date`: «14. marts», «14.03.1946», «1946-03-14». 422 ved en dato, der ikke findes |
| PATCH | `/privat/birthdays/{id}` | `{remind_days_before: 0–60}` |
| DELETE | `/privat/birthdays/{id}` | 204 |

`Birthday`: `{id, name, month, day, year, date_text, next_date, days_until, turns, remind_days_before}`. Alle kræver appen slået til
(`403 addon_disabled`).

**Påmindelsen** sendes af hovedworkerens faste job: `remind_days_before` dage før (standard 7, 0 = på dagen), tidligst kl. 08
dansk tid, med push eller – uden push-abonnement – e-mail, ét link til `/privat/foedselsdage`. Én gang pr. fødselsdag pr. år
(`last_reminded_for`); en påmindelse, der blev misset (worker nede), kommer stadig, frem til selve dagen. 29. februar mindes
den 28. februar i andre år. Slået appen fra, sendes intet; data beholdes.

**Assistentens værktøjer:** `add_birthdays(items[{name, date, remind_days_before?}])`, `list_birthdays()`, `remove_birthday(name)`.

## Regninger (tilføjelsen «Regninger»)

Faste regninger, brugeren selv fortæller om. Kode: `app/modules/privat/bills.py`, endpoints i `app/modules/privat/apps_router.py`.
Med i Plus og Familie. **Dialogbot betaler aldrig og har ingen adgang til banken.** Gemt: navn, beløb (kun når brugeren siger det),
hyppighed og næste forfaldsdato.

| Metode | Sti | Svar |
|---|---|---|
| GET | `/privat/bills` | `{items: [Bill], month: {month, total_minor, total_text, without_amount, items}}` – månedens regninger og summen af de kendte beløb |
| POST | `/privat/bills` | `{name, amount?, frequency?, due_date? \| due_day?, remind_days_before?}` → `Bill + {created}`. Samme navn retter regningen. `frequency`: `monthly`, `quarterly`, `half_yearly`, `yearly`, `once`. 422 uden dato eller ved et beløb, der ikke kan læses |
| PATCH | `/privat/bills/{id}` | `{remind_days_before: 0–30}` |
| DELETE | `/privat/bills/{id}` | 204 |

`Bill`: `{id, name, amount_minor, amount_text, frequency, frequency_text, next_due, due_text, days_until, remind_days_before}`.

**Påmindelsen** (hovedworkerens faste job, sammen med Fødselsdage): `remind_days_before` dage før (standard 3), tidligst kl. 08,
push eller e-mail, én gang pr. forfaldsdato. Når datoen er passeret, rykker en fast regning videre (`anchor_day` holder «den 31.»
på månedens sidste dag i korte måneder); en engangsregning bliver stående, til brugeren fjerner den.

**Assistentens værktøjer:** `add_bills(items[{name, amount?, frequency?, due_day?, due_date?, remind_days_before?}])`,
`bills_overview()`, `remove_bill(name)`.

## Pakkeliste, Madplan, Læge & tandlæge, Bil & syn, Pakker

Fælles: indstillinger pr. app i `private_app_data` (JSON, kun det brugeren selv gav). Alle med i Plus og Familie; alle endpoints
kræver appen slået til (`403 addon_disabled`). Kode: `app/modules/privat/{packing,meals,health,car,parcels}.py`, endpoints i
`app/modules/privat/apps_router.py`.

**Pakkeliste.** En pakkeliste er en almindelig liste («Pakkeliste: <tur>»); appen husker hvilke. Værktøjer:
`create_packing_list(trip, items[])`, `reuse_packing_list(trip?)` – kopierer den seneste, intet krydset af.

**Madplan.** `GET/PUT /privat/meals/preferences` `{people, avoid, likes}`. Værktøjer: `save_food_preferences`,
`get_food_preferences`, `save_meal_plan(title, days[{day, dish, ingredients[]}], shopping_list?)` – først når brugeren har sagt ja;
giver en liste med retterne og én indkøbsliste, hvor samme vare kun står én gang.

**Læge & tandlæge** (kræver «Ring for mig», som slås til med). `GET /privat/health-contacts`, `DELETE /privat/health-contacts/{kind}`.
Gemmer kun klinikkens navn og det nummer, brugeren selv skrev – aldrig helbredsoplysninger. `book_health_appointment` laver et
almindeligt opkaldsforslag (der ringes aldrig uden godkendelse) med «Fortæl ikke andet om mit helbred end det, der står i formålet».

**Bil & syn** (kræver «Ring for mig»). `GET/PUT /privat/car` `{plate, inspection_due, service_due, tire_reminders}` (+ `workshop`,
`summary`). Datoerne skrives af brugeren – intet opslag på nummerpladen. Påmindelser (hovedworkerens faste job, tidligst kl. 08,
hver én gang): syn 30 dage før, service 14 dage før, vinterdæk fra 15. oktober og sommerdæk fra 25. marts. `book_workshop` er et
opkaldsforslag til det gemte værksted.

**Pakker.** Kræver `TRACK17_API_KEY` (17TRACK); uden den er appen «Kommer snart» (`Addon.needs_setting`). `GET/POST /privat/parcels`
`{number, label?}`, `DELETE /privat/parcels/{number}`. Kun forsendelsesnummeret sendes til 17TRACK. Workeren spørger højst hver 2.
time for pakker, der ikke er leveret, og giver besked ved på vej / ude til levering / klar til afhentning / leveret / problem.
17TRACK-kaldene er ikke prøvet mod en rigtig nøgle.

## Rejser (trin 1: forslag med rigtige priser, booking hos udbyderen)

Kode: `app/modules/privat/travel.py`. Med i Plus og Familie. Kræver mindst én prisudbyder, ellers «Kommer snart»:
`DUFFEL_ACCESS_TOKEN` (Duffel: flytilbud på præcise datoer, samlet pris) og/eller `TRAVELPAYOUTS_TOKEN` + `TRAVELPAYOUTS_MARKER`
(Travelpayouts/Aviasales: billigste cachede priser pr. rute og måned, med affiliate-link). **Peter opfinder aldrig en pris**:
et forslag uden pris fra en udbyder vises ikke.

| Metode | Sti | Svar |
|---|---|---|
| POST | `/privat/trips/search` | `{origin, destinations[≤5], depart_date? \| month?, nights?, adults, children, budget_dkk?, trip_type?, direct_only?}` (IATA-koder) → `{id, params, offers[], over_budget, errors[]}`. Billigst først, inden for det samlede budget |
| GET | `/privat/trips/latest` | `{search}` – den seneste søgning (de 5 seneste gemmes) |

`offer`: `{id, provider, origin, destination, total_dkk, airline, depart_at, return_at, stops, book_url, price_note}`.
**«Book»** åbner udbyderens side (Travelpayouts-link med Dialogbots marker; for Duffel-tilbud en flysøgning for samme rute og dato).
Der bookes og betales intet i Dialogbot i trin 1. Trin 2 (booking i Dialogbot via Duffel) kræver juridisk afklaring
(Rejsegarantifonden ved pakkerejser) og er ikke bygget.

**Assistentens værktøj:** `search_trips(...)` – nævner brugeren en rejsetype i stedet for et sted, vælger modellen 3-5 destinationer.
Udbyder-API'erne er ikke kaldt med rigtige nøgler (svarformatet er fra dokumentationen).


## Husstandens apps (Abonnementer, Håndværker & tilbud, Fælles udgifter, Garanti, Fest, Flytning, Kæledyr, Hus, Fitness)

Alt sker i chatten; appens panel viser en oversigt. Data ligger i `private_app_data` under appens nøgle
(`app/modules/privat/app_kit.py`).

| Endpoint | Svar |
|---|---|
| `GET /privat/apps/{key}/overview` | `{summary, items: [{id, text, sub, share_text?}], partner: {category, name, url, text, note} \| null}`. 403 `addon_disabled` når appen er slået fra, 404 for en ukendt app. |
| `DELETE /privat/apps/{key}/items/{id}` | 204; 404 når den ikke findes. |
| `POST /privat/apps/{key}/items/{id}/photo` | Billedet som rå body (JPEG/PNG/WebP/HEIC, ≤ 6 MB). Kun Garanti. Oversigten giver `photo_url` (5 min.). |
| `PATCH /privat/me/assistant` `{name, pronoun?}` | Assistentens navn (1–20 bogstaver; tomt = «Peter») og `pronoun` han/hun/den (tomt = han for Peter, den for alle andre navne – aldrig gættet). Svarer som `GET /privat/me`, der har `assistant_name` og `assistant_pronoun`. |
| `GET /operator/privat/business-referrals?days=` | Kun operatør: lead-regnskabet pr. virksomhed `{items: [{business_name, phone, asked, chosen, last_at}]}`. |

`key`: `abonnementer`, `haandvaerker`, `faelles-udgifter`, `garanti`, `fest`, `flytning`, `kaeledyr`,
`hus-og-vedligehold`, `fitness-og-sundhed`. Funnel-svaret `assistant_name` (skærm 1 på /privat/start) bliver
kontoens navn, når kontoen oprettes.

Regler, der ligger i koden:
- Dialogbot ringer aldrig uden godkendelse og siger aldrig ja til en pris, en aftale, en ny binding eller betaling.
- Numre bruges kun, når brugeren selv har skrevet dem (dyrlæge, opsigelse pr. telefon) – eller fra virksomhedssøgningen
  (Håndværker & tilbud).
- Partnerlinks vises kun med «Annonce – Dialogbot kan få provision», kun over https, og aldrig ved siden af de
  virksomheder, brugeren har bedt om tilbud fra.
- Tekster, brugeren sender videre (opsigelse, reklamation, invitation, opgørelse), slutter med Dialogbots fodlinje.
- Fitness & sundhed gemmer aldrig vægt, sygdom, skader, medicin eller andre helbredsoplysninger.
- Påmindelser: én pr. dato og app, fra kl. 8 dansk tid, push eller e-mail, kun mens appen er slået til; linket går til
  `/privat/apps/{key}`.

Madplan (udvidet): `save_meal_plan` tager `people` og pr. ret `servings`; mængderne regnes om og lægges sammen på
indkøbslisten («500 g» + «250 g hakket oksekød» = «750 g hakket oksekød»), og hver dags ingredienser står som note på
dagen.

## Ønsker, fællesgaver og design (tilføjelsen «Ønskelister»)

Bygget oven på de delte ønskelister (samme `private_tasks`/`private_task_items`, samme medlemskab, invitationer og hemmelige
reservationer) – ingen parallelle systemer. Moduler: `wishes.py` (felter, import, søgning), `product_meta.py` (læser
butikkens strukturerede data), `safe_fetch.py` (SSRF-sikker hentning), `wish_images.py` (billeder), `group_gifts.py`
(fællesgaver), `wish_design.py` (design); ruter i `wishes_router.py`. Migration `d8e4a1c6f2b9` er rent additiv.

### Et ønske – én datamodel

`TaskItem` har nu (alle valgfrie, gamle punkter er uændrede): `quantity` (standard 1), `price_minor` (valutaens mindste
enhed) + `currency` (ISO, standard `DKK` når der er en pris), `price_source` (`shop` = læst fra butikkens side ved
`price_fetched_at`, `user` = skrevet af ejeren – priser opdateres aldrig løbende), `shop`, `size`, `color`, `variant`,
`image` (`{url, url_sm}`, signerede 5-minutters links til vores egen kopi), `image_origin` (`shop`|`upload`),
`details` (`brand`, `sku`, `availability`, `description`, `options` = de varianter siden selv oplyser), `group_gift`
(se nedenfor) og `archived` (kun for gavegivere med en aftale på et ønske, ejeren har slettet). `Task.design` er
ønskesedlens udseende.

| Metode | Sti | Hvem | Hvad |
|---|---|---|---|
| GET | `/privat/wishes/search?q=` | alle | «Søg efter produkt»: rigtige produktsider (websøgning + hver sides egne strukturerede data). `503 search_unavailable` uden websøgning. 30/time (429). |
| POST | `/privat/wishes/import` `{link}` | alle | «Indsæt link»: `{link, readable, reason, fetched_at, title, price_minor, currency, shop, size, color, variant, details, options, image_key, image}`. Kan siden ikke læses: `readable:false` + linket. Interne/ulovlige adresser: 422. 60/time. Gemmer intet på listen. |
| POST | `/privat/wishes/images` (rå JPEG/PNG/WebP ≤ 6 MB) | alle | Eget billede → `{image_key, image}` til formularen. |
| POST | `/privat/tasks/{id}/wishes` | ejer (ønskeliste) | Opret ønske (`WishIn`: `text` + felterne ovenfor + `image_key`, `group_gift_enabled`, `group_gift_target_minor`). |
| PATCH | `/privat/tasks/{id}/wishes/{item}` | ejer | Ret ønske (kun de sendte felter). |
| DELETE | `/privat/tasks/{id}/items/{item}` | ejer | Som før. Har gavegivere en aftale (tilsagn eller «Købt»), arkiveres ønsket i stedet: ejeren ser det forsvinde, gavegiverne ser «Annulleret» og får besked. |
| PUT | `/privat/tasks/{id}/items/{item}/gift/pledge` `{amount_minor}` (+ `Idempotency-Key`) | gavegiver | Meld dig til / ret dit beløb. Over restbeløbet: `409 pledge_exceeds_remaining` med `remaining_minor` (aldrig lydløst ændret). Fuld: `409 gift_full`. Købt: `409 gift_bought`. Reserveret separat: `409 already_reserved`. |
| DELETE | `/privat/tasks/{id}/items/{item}/gift/pledge` | gavegiver | Annuller eget tilsagn (idempotent). |
| POST | `/privat/tasks/{id}/items/{item}/gift/coordinator` `{action, to?}` | deltager | `take` (kun når ingen har rollen), `transfer` (koordinator → anden deltager, `to` = `user_ref`), `accept`/`decline` (modtageren), `cancel_transfer`, `release`. |
| POST | `/privat/tasks/{id}/items/{item}/gift/bought` `{bought}` | koordinator | Markér som købt (eller fortryd). Summen markerer aldrig noget som købt. |
| PUT | `/privat/tasks/{id}/design` `{title?, design}` | ejer | Gem design; `design: null` = standardtemaet. Påvirker kun designet. |
| POST | `/privat/tasks/{id}/design/cover` (rå billede) | ejer | Upload cover → `{key, image}`; bruges først ved «Gem design». |

### Fællesgave («Deles om en gave») – koordinering af tilsagn, ingen betaling

- Ejeren slår «Tillad fællesgave» til og foreslår et målbeløb (standard: prisen). Ejeren ser **kun** sin indstilling:
  `group_gift: {enabled, target_minor, currency}` – aldrig aftalen, status, beløb, deltagere eller koordinator. Alle
  gavegiver-ruter svarer ejeren `403 owner_cannot_give` uanset tilstand. Ingen events, `updated_at`, chat eller
  notifikationer til ejeren.
- Gavegivere er medlemmer af den delte ønskeliste (login + personlig invitation). De ser `group_gift: {enabled, status
  (open|full|bought|cancelled), target_minor, currency, pledged_minor, remaining_minor, participants, my_pledge_minor,
  coordinator {name, is_me}, pending_coordinator_is_me, is_coordinator, can_join, reserved_by_me, participant_names
  (kun koordinatoren, ingen beløb)}`. Ingen ser andres beløb.
- Aftalens mål kopieres fra ønsket ved første tilsagn og ligger derefter fast. Én valuta pr. aftale. Alle skrivninger
  låser ønskets række (`SELECT … FOR UPDATE`), så samtidige tilsagn aldrig overtegner målet; ét tilsagn pr. person
  (unik), så dobbeltklik/genforsøg opdaterer samme række.
- Ejeren slår fællesgave fra / sletter ønsket: en åben aftale annulleres (tilsagnene gemmes), deltagerne får
  push/e-mail. En reservation og en aktiv fællesgave udelukker hinanden (`409 group_gift_active` / `already_reserved`).
- Forlader en gavegiver listen, ophører vedkommendes åbne tilsagn og roller.
- Offentligt invitations-preview viser kun `group_gift_count` (ejerens indstilling) og temaets farver – aldrig cover,
  ønsker, beløb eller personer.

### Design

`design: {theme, accent, background, text, font, decorations, subtitle, date, cover {key, url, url_sm, zoom, x, y},
overrides, customized}`. Ti temaer (`jul`, `foedselsdag`, `bryllup`, `konfirmation`, `barnedaab`, `babyshower`,
`student`, `jubilaeum`, `indflytning`, `neutral`), fire skrifter (`outfit`, `inter`, `serif`, `rounded`). Serveren
accepterer kun disse nøgler, `#RRGGBB` og egne cover-nøgler, og kræver WCAG-kontrast (tekst/baggrund ≥ 4,5, hvid
knaptekst på accent ≥ 4,5, accent/baggrund ≥ 3). Paletten spejles i `web/src/lib/privat/wish-themes.json` (en test holder
dem ens).

### Sikkerhed ved hentning (SSRF)

Kun http/https på port 80/443, ingen brugernavn/kode i URL'en; alle DNS-svar skal være offentlige adresser (ingen
loopback, private net, link-local/metadata, CGNAT, multicast, IPv4-mappede varianter); forbindelsen går til den
kontrollerede IP (værtsnavnet kun i Host/SNI), så DNS-rebinding ikke virker; omdirigeringer følges manuelt (højst 4) og
kontrolleres hver gang; 8 s timeout; 2 MB HTML / 6 MB billede. Indholdet behandles som data (ingen scripts køres).
`links.py` («Hvor kan den købes?») bruger nu samme fetcher.

## Apps: Mine apps og Butikken

Fanen «Apps» har to sider: **Mine apps** (`/privat/apps`) og **Butikken** (`/privat/butik`). En app har en butiksside
(`/privat/butik/<key>`, før den er slået til) og sin egen side (`/privat/apps/<key>`, når den er – eller har været – slået
til). De gamle stier (`/privat/kalender`, `/privat/foedselsdage`, `/privat/regninger`, `/privat/bil`, `/privat/pakker`)
åbner appens egen side. Ark bruges kun til bekræftelser: «Slå X til?» (samtykke til «Den får lov til»), «X kræver Plus»
(planvalg) og «Slå X fra?» (hvad stopper, hvad gemmes, hvilke apps der også slås fra) – med «Fortryd» bagefter.

`Addon` har nu også (alle valgfrie for ældre klienter):

| Felt | Betydning |
|---|---|
| `needs` | «Du skal bruge» (katalogfeltet `needs`) |
| `summary_line` | Hvad appen holder for brugeren lige nu («Syn om 34 dage · 8. dec.»), kun mens den er slået til; ellers `null` → tagline (`app_status.py`) |
| `setup` | `{done, total}` – opsætningstrin klaret; standard-apps (`PRIVAT_DEFAULT_ADDONS`) starter som færdige |
| `disabled_at` | Slået fra – data gemt («Slået fra · dine data er gemt»); `null` mens den er slået til, eller hvis den aldrig er brugt |
| `notify_requested` | «Giv mig besked» for en «Kommer snart»-app |
| `data_deletable` | Appens egne data kan slettes fra appen (ikke lister/opgaver/opkald) |

| Metode | Sti | Hvad |
|---|---|---|
| PUT | `/privat/addons/{key}/setup` `{done}` | Opsætningsfremskridt (409 `addon_disabled`, 422 uden for 0…len(steps)) |
| POST | `/privat/addons/{key}/notify` | «Giv mig besked» gemmes på kontoen |
| DELETE | `/privat/addons/{key}/data` | Slet en slået-fra apps data (409 `addon_enabled` / `not_deletable`). Kan ikke fortrydes. |
| POST | `/privat/subscription/checkout` `{…, app}` | `app`: appen, der krævede planen – den slås til, når planen er på plads (Checkout-metadata), og brugeren lander på `/privat/apps/<key>` |

Tabellen `private_addon_state` (migration `e3b7c9d1a5f4`, additiv) holder fremskridt, `disabled_at` og «Giv mig besked».
Om en app er slået til er stadig `private_addon_enabled`. En app, der var slået til, da planen sluttede, kører videre
(«Once on, it stays on»); slås den fra, kræver det planen at slå den til igen.

Webbens simulering (`web/src/lib/privat/fake.ts`) læser det samme katalog: `web/src/lib/privat/addons-catalog.json`,
genereret med `python -m scripts.export_privat_catalog` (CI fejler, hvis filen afviger fra `addons.py`).

