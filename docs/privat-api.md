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
ChatMessage = {id, role: "user"|"assistant", kind: "text"|"task"|"move"|"clarify"|"call_proposal"|"draft"|"waiting",
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
POST /privat/calls/{task_id}/approve {window, share_phone} (Idempotency-Key) → Task   // 409 needs_phone | insufficient_credits | outside_hours
POST /privat/calls/{task_id}/decline          → Task
POST /privat/calls/{task_id}/retry            → Task (tilbage til awaiting_user med nyt forslag)
POST /privat/phone/start {phone}              → {sent: true}          // SMS-kode, 6 cifre, 10 min
POST /privat/phone/verify {code}              → Balance
POST /privat/credits/checkout                 → {url}                 // Stripe Checkout mode=payment, 10 credits («ekstra opkald»), 29,00 kr. inkl. moms
GET  /privat/subscription                     → Subscription          // ?session_id=cs_… synkroniserer først fra Stripe Checkout-sessionen
POST /privat/subscription/checkout {plan, interval} → {url}           // Stripe Checkout mode=subscription
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
  plans: Plan[]                                                       // kataloget (frontend hardcoder ingen priser)
}
Plan = {key, name, monthly_minor, yearly_monthly_minor, yearly_total_minor, calls, people, apps_included, recommended: bool, features: string[]}
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
  joined_via_invite_id|null). Kun ejeren ser gruppen. Numrene bruges KUN til at brugeren selv kan sende fra sin egen telefon og til at
  genkende, når personen allerede er på Dialogbot – vi kontakter dem aldrig selv, ingen markedsføring, slettes med gruppen/kontoen.
- Smart opbygning: (1) «Folk du har delt med» – personer der har accepteret brugerens invitationer foreslås automatisk (med navn);
  (2) vælg fra kontakter (Android Contact Picker) – kun de valgte gemmes, efter et klart «Gem i gruppen»; (3) skriv navn + nummer;
  (4) indsæt flere numre på én gang (komma/linjeskift, normaliseres til +45); (5) i chatten: «Del ønskelisten med familien»
  → bruger gruppen; findes den ikke: «Skal jeg lave gruppen Familien med Anna, Peter og Mor?» (forslag, kræver ja).
- Når der deles med en gruppe:
  * medlemmer der allerede har Dialogbot (user_id kendt eller verificeret telefon matcher) tilføjes DIREKTE til listen og får besked i
    appen (+ push senere) – ingen SMS nødvendig;
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

---

# Implementering (backend, app/modules/privat) – afvigelser og præciseringer

Alt ovenfor er implementeret. Afvigelser er bagudkompatible (kun ekstra felter/endepunkter) og står her.

## Generelt
- Feature-flag: `PRIVAT_ENABLED` (standard false) + `PRIVAT_ALLOWED_EMAILS` (kommaliste; tom = alle). Uden adgang: 403 `privat_not_enabled`.
  Offentlige invitationsendepunkter svarer 404 `invite_invalid`, når flaget er slået fra.
- Privat konto kræver bekræftet e-mail (403 `email_not_verified`). GET-endepunkter uden konto: 404 `privat_account_missing`;
  POST-endepunkter opretter kontoen automatisk (samme som `POST /privat/account`).
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
- Påmindelsesstatus: planned → done, når påmindelsen er sendt (e-mail nu; push er en tom krog: `service.push_hook`).

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
- Virksomhedsopslag: i piloten skal brugeren selv skrive navn + nummer (nummeret skal stå i brugerens egne beskeder – modellen kan
  ikke opfinde det), eller vælge fra et lille fiktivt Aarhus-fixture (Cykelmageren / Østbyens Cykler). Fixture-numrene må kun ringes
  op i dev/test (409 `demo_business` ellers). **Rigtigt virksomhedsopslag (Google Places/CVR) er fremtidigt arbejde.**
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
- OG-billede (`/privat/og/invite/{token}.png`) er ikke lavet i backend – web bruger Next opengraph-image (titel + fornavn + mærke, aldrig varer).

## Nye miljøvariabler
`PRIVAT_ENABLED`, `PRIVAT_ALLOWED_EMAILS`, `PRIVAT_POOL_NUMBERS`, `PRIVAT_STRIPE_PRICE_ID` (valgfri; ellers inline-pris 2900 øre
inkl. moms), `PRIVAT_STRIPE_PRICE_{BASIS,PLUS,FAMILIE}_{MONTH,YEAR}` (valgfri faste Stripe-priser for abonnementerne; ellers inline
price_data), `PRIVAT_DEFAULT_ADDONS` (standard `ring-for-mig,delte-lister,oenskelister`), `PRIVAT_SHORT_URL_BASE`
(standard `https://dialogbot.app/i/`), `PRIVAT_GROUP_URL_BASE` (standard `https://dialogbot.app/g/`).
