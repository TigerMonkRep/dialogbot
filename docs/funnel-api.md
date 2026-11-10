# Quiz-funnels – API-kontrakt (Erhverv `/start`, Privat `/privat/start`)

Alle under `/api/v1/funnel` (web-proxy: `/api/backend/funnel/...`). **Ingen login** før reveal. Backend: `app/modules/funnel/`
(router, service, estimates, privat_seed, limits), tabel `funnel_drafts` (migration `f1a2b3c4d5e6`). Fejl følger repoets
ApiError-format. Tider ISO 8601 med tidszone.

Idéen: ét spørgsmål pr. skærm; svarene gemmes i en **draft uden konto**. Reveal kræver gaten (navn, e-mail, mobil → SMS-kode);
først dér oprettes bruger, session og (Erhverv) arbejdsrum + demo-opkald / (Privat) privat konto + opgaver.

## Typer

```
Draft = {
  id, kind: "erhverv"|"privat", hook|null, industry|null, step: int, answers: {...},
  company: {name, address, phone_display, phone_e164|null, website|null, opening_hours_text|null, place_id|null,
            postal_code|null, city|null, source: "google"|"demo"|"fixture"|null} | null,           // erhverv, efter trin 2
  estimate: {missed_per_week: int, source: string} | null,                                           // erhverv, efter trin 3
  build: {knowledge: "pending"|"done"|"skipped", voice: "done", voice_key: "peter"|"camilla",
          hours: "done"|"default", number: "done"|"pending", pages_count?: int, knowledge_import?: "running"}  // erhverv
       | {tasks: int, lists: int, first_call: {title}|null, items: [{kind, title, key?}]},                     // privat
  gated: bool, verified: bool, phone_display|null, expires_at, next: string|null                      // next sat efter verify
}
```

`build.knowledge`: `pending` = hjemmeside kendt, ikke hentet endnu (hentes ved trin 4) · `done` = siderne er hentet og ligger på
draften (importeres som **ikke-godkendte** kladder ved verify) · `skipped` = ingen hjemmeside, demodata, eller hentningen fejlede.
`build.number`: `done` når Dialogbots demo-linje er klar (`GET /demo-call` → available), ellers `pending`.
`build.hours`: `done` når Google kender åbningstiderne, ellers `default`.

## Endepunkter

```
GET  /funnel/industries                       → {industries: [{key, label, playbook, voice}], missed: [...], estimate_source}
GET  /funnel/consent                          → {version, erhverv: tekst, privat: tekst}          (samtykketeksten ved gaten)
POST /funnel/drafts                           {kind, hook?, industry?, utm?: {source, medium, campaign, content}} → 201 Draft
GET  /funnel/drafts/{id}                      → Draft                       (404 draft_not_found | draft_expired)
PATCH /funnel/drafts/{id}                     {step: 1..7, answers: {...}} → Draft   (idempotent; svar flettes)
GET  /funnel/places?q=…&industry=…            → {items: [{place_id, name, address, phone_display, website, open_now, source}]}
POST /funnel/drafts/{id}/gate                 {name, email, phone, consent: true, website?: ""} → 202 {status: "code_sent", phone_display}
POST /funnel/drafts/{id}/verify               {code} → {status: "ok", next, session_token, access_token, token_type: "bearer",
                                                       user: UserOut, new_user: bool, workspace_id|null}
GET  /funnel/drafts/{id}/reveal               (Bearer-session for draftens bruger) →
        {kind, call: {status, outcome, summary, duration_seconds, error}|null, call_problem|null, workspace_id|null, next,
         knowledge: {status, import: Import|null}|null, company|null, created: {task_ids, first_call_task_id}|null}
```

### Erhverv – svar pr. trin (answers)

| Trin | answers | Bagved |
|---|---|---|
| 1 | `industry`: haandvaerker · klinik · salon · vaerksted · raadgiver · restaurant (salgsscriptets nøgler accepteres også) | gemmes; `build.voice_key` = branchens standardstemme |
| 2 | `company_name` (+ `place_id` fra `/funnel/places`) | Places-opslag (privat/places-klienten: Google med nøgle, ellers demodata) → `company`, `build.hours`; hjemmeside → `build.knowledge: pending` |
| 3 | `missed`: [lunch, after16, driving, weekend, never_free], `missed_per_week?` (brugerens eget tal vinder) | `estimate` fra tabellen i `estimates.py` (`source` = «Dialogbots skøn for branchen …» / «Dit eget tal») |
| 4 | `wants`: [book, message, prices] | starter hentning af hjemmesiden i baggrunden (siderne gemmes på draften) |
| 5 | – | poll `GET /drafts/{id}` til `build.knowledge` ≠ pending |

### Privat – svar pr. trin

| Trin | answers | Bagved |
|---|---|---|
| 1 | `postponed`: [dentist, bike, car_inspection, gift, doctor, hairdresser, insurance, landlord] | opkald-kladder (call) eller påmindelser (`privat_seed.POSTPONED`) |
| 2 | `household`: alone · couple · kids · parents | standardlister (indkøb; pakkeliste ved kids; fødselsdage ved parents) |
| 3 | `hate_calls`: health · workshop · municipality · restaurant | kun gemt (eksempelteksten er statisk i web) |
| 4 | `remind_at`: morning · lunch · evening | påmindelser i morgen kl. 08/12/19 Europe/Copenhagen |
| 5 | – | `build` = forhåndsvisning (`tasks`, `lists`, `first_call`) – intet er oprettet |

## Gate og verify

- `phone` skal være et dansk nummer (8 cifre, ikke 90xx). Samme SMS-vej som Privat (`privat/phone.py`: Twilio-hovedkontoen, afsender
  «Dialogbot»; simuleret med `CONNECTORS_PROVIDER=fake` eller i dev/test uden telefoni). 6 cifre, 10 minutter, 5 forsøg; ny kode tidligst
  efter 30 s (`409 too_soon`). Kun en HMAC af koden gemmes.
- Honeypot: udfyldt `website` → `202 code_sent` med `phone_display: null`, intet gemt, ingen SMS.
- Privat: `PRIVAT_ENABLED`/`PRIVAT_ALLOWED_EMAILS` tjekkes allerede ved gaten (`403 privat_not_enabled`).
- Fejl ved verify: `422` (forkert kode, `attempts_left`), `409 code_expired | too_many_attempts | draft_verified`.
- **Ny e-mail** → User med tilfældig adgangskode, `users.phone_verified_at` sat, e-mail **ikke** verificeret, velkomstmail
  (`email.branded`) med «Vælg adgangskode»-link = det almindelige `/password/reset?token=…` (gyldigt `VERIFICATION_TTL_HOURS`).
  Audit `user.registered` (`source: "funnel"`, `proof: "sms_code"`).
- **Kendt e-mail** → **ingen session** og ingen ændring på kontoen: SMS-koden beviser kun ejerskab af det tastede nummer, ikke af
  kontoen bag e-mailen. Svar `409 account_exists` («Der findes allerede en konto med den e-mail. Log ind for at fortsætte.»); audit
  `funnel.account_exists` (user_id + det tastede nummer); intet arbejdsrum/privatkonto; kladden får ingen `user_id`. Web viser «Log ind»
  (→ `/login`). Gælder også deaktiverede konti (afslører ikke deaktivering). (Hotfix #177, F-P2-01-X04/F-E2A-01-X03.)
- Session: `start_session` som `POST /auth/login`; svaret bærer `session_token` **og** `access_token` (samme værdi) + `user`, så BFF'en
  sætter sin httpOnly-cookie præcis som `/api/auth/login`. `workspace_id` returneres, så web også kan sætte arbejdsrums-cookien.
- Efter verify er draften låst (`409 draft_verified` på PATCH/gate/verify), men `GET` og `reveal` virker.

### Erhverv ved verify
1. Arbejdsrum (`kind=business`, `product_intent=reception`, ejer = brugeren) – uden krav om verificeret e-mail (`create_workspace(require_verified=False)`).
2. Virksomhedsprofil: `legal_name` = Places-navnet (ellers det indtastede), `description` (branche + adresse), `website_url`, adresse/postnr/by,
   `phone` = Places-nummeret, `version` 2 → `/opsaetning/1` læser trin 1 som udfyldt (navn + beskrivelse + telefon). Trin 2 springes over
   (ingen booking valgt). Kategori (primær) fra branchen; `workspace_voice_settings.standard_voice` = branchens stemme.
3. Viden: åbningstider fra Google som **kladde** (`source_type: import`), og de hentede sider importeres med den eksisterende website-import
   (`SourceImport` + `importer.run(pages=…)`, AI-udtræk) → kladder med `source_type: extraction`. Intet godkendes. `reveal.knowledge.import` viser status.
4. Demo-opkald: `sales.service.request_web(phone, name, company, industry, context)` – Peter ringer til det bekræftede nummer, første replik
   nævner firmanavnet, og manuskriptet får en faktasektion (`demo_calls.context`: adresse, åbningstider fra Google, hjemmeside, hvornår de
   mister opkald, skønnet, hvad receptionisten skal kunne). Samme regler som «Ring mig op nu»: kun i opkaldstiden, ét web-opkald pr. nummer
   pr. døgn, spærreliste, global grænse. Kan der ikke ringes, fejler verify **ikke**: `reveal.call = null` og `call_problem` forklarer.
5. `next = "/start/klar"`.

### Privat ved verify
`deps.ensure_account` (prøveperiode starter, standard-tilføjelser), profilens nummer sættes verificeret, og `privat_seed.create` opretter de
rigtige rækker gennem chattens egne veje: lister (`in_progress`), påmindelser (`planned`, outbox-event ved `remind_at`), og opkald som
**forslag uden nummer** (`awaiting_user`, besked «Jeg har ikke et nummer til … Skriv nummeret her») – svaret med et nummer om opgaven
sætter nummeret som i chatten. Intet ringes. `next = "/privat/dag?velkommen=1"`.

## Regler

- Rate-limit pr. IP (`limits.py`, X-Forwarded-For først): drafts 20/t, PATCH 300/t, places 30/t, gate 5/t, verify 30/t, plus globale lofter.
  BFF'en skal sende den besøgendes adresse i `X-Forwarded-For`. `429 rate_limited`.
- Draft-id'et er hemmeligheden (cookie `dialogbot_funnel`, 7 dage). `GET` viser aldrig gate-data ud over `gated`/`phone_display`.
- Rækker uden verificeret bruger slettes af workerens planlagte job 7 dage efter oprettelsen (`service.purge_expired`); efter udløb svarer
  API'et `404 draft_expired`.
- Ingen opkald før brugeren selv har tastet nummeret og bekræftet koden. Crawlet viden er altid ikke-godkendte kladder. Skønnet vises med kilde
  («Dialogbots skøn for branchen …») og kan rettes – det er ikke en statistik.
