# Dialogbot Public API v1

`https://api.dialogbot.app/v1` – fase 1 og 2 af forslaget *Dialogbot Public API (v1) + MCP-server* (2026-11-07): ApiKey,
read-only Erhverv, webhooks. Koden ligger i
`app/modules/public_api/`; kontrakten er `docs/public-openapi.json` (genereres med `python -m scripts.export_public_openapi`,
CI sammenligner). Interaktiv dokumentation: `/v1/docs`.

Den interne API (`/api/v1`, bruges af `/app` og `/privat`) er uændret og dokumenteret i `api-contract.md`. Den offentlige
API er en *separat, stabil delmængde* med egne, frosne svar-skemaer (`public_api/schemas/v1.py`) – aldrig ORM-modellerne.

## Hurtigt i gang

1. I appen: **Integrationer → API-nøgler** (owner/admin) → *Opret nøgle* med navn og scopes. Nøglen (`dbk_live_…`) vises
   **én gang**. Internt endpoint: `POST /api/v1/workspaces/{id}/api-keys` `{name, scopes[], environment?, expires_in_days?}`.
2. Kald:

   ```bash
   curl https://api.dialogbot.app/v1/me -H "Authorization: Bearer dbk_live_…"
   curl "https://api.dialogbot.app/v1/workspaces/$WS/calls?limit=20" -H "Authorization: Bearer dbk_live_…"
   ```

3. Abonnér på hændelser: `POST /v1/workspaces/{id}/webhooks` (se nedenfor).

Højst **2 aktive nøgler** pr. arbejdsrum (rotation: opret den nye, skift, tilbagekald den gamle). `environment: test`
giver præfikset `dbk_test_` – i dag er det kun en mærkning af nøglen til jeres testopsætning; den læser samme data som
en live-nøgle. Udløb er valgfrit (`expires_in_days`, højst 3650). Tilbagekaldelse (`DELETE …/api-keys/{id}`) virker
øjeblikkeligt. Oprettelse og tilbagekaldelse står i arbejdsrummets revisionslog.

## Auth og fejl

`Authorization: Bearer dbk_live_…` på hvert kald. Nøglen er bundet til ét arbejdsrum; `workspace_id` i stien skal være
det – ellers `404`. Kun SHA-256 af nøglen gemmes (som sessioner); `last_used_at` opdateres højst én gang i minuttet.

| Status | `code` | Hvornår |
|---|---|---|
| 401 | `unauthenticated` | Ingen bearer-token |
| 401 | `api_key_invalid` | Ukendt, tilbagekaldt eller udløbet nøgle, eller lukket arbejdsrum (svaret siger ikke hvilket) |
| 403 | `insufficient_scope` | Nøglen mangler scopet; `required_scope` i svaret |
| 404 | `not_found` | Andet arbejdsrum, eller objektet findes ikke i nøglens arbejdsrum |
| 409 | `idempotency_payload_mismatch` | Samme `Idempotency-Key`, andet indhold |
| 422 | `validation_failed`, `idempotency_key_required`, `invalid_cursor`, `url_not_allowed` | Input |
| 429 | `rate_limited` | Se *Rate limits*; `Retry-After` i sekunder |

Fejlkonvolutten er den samme som i den interne API: `{code, message, field_errors, request_id}`. `X-Request-ID` er på
hvert svar – send det med, når I skriver til support.

## Scopes

Scopes mappes på appens rettigheder (`app/core/auth.PERMISSIONS`); en admin kan ikke give et scope, admin ikke selv har.

| Scope | Giver adgang til | Rolle i appen |
|---|---|---|
| `calls:read` | `GET …/calls`, `…/calls/{id}` | staff |
| `conversations:read` | `GET …/conversations`, `…/{id}`, `…/{id}/messages` | staff |
| `bookings:read` | `GET …/bookings`, `…/bookings/{id}`, `…/booking-types` | staff |
| `leads:read` | `GET …/leads`, `…/leads/{id}` | staff |
| `knowledge:read` | `GET …/knowledge`, `…/knowledge/{item_id}` – kun godkendte, offentlige versioner | reader |
| `campaigns:read` | `GET …/campaigns`, `…/do-not-call` | staff |
| `campaigns:write` | `POST …/do-not-call` | staff |
| `reports:read` | `GET …/reports/daily`, `…/reports/daily/{date}` | staff |
| `contacts:read` | Telefonnumre og e-mails i klartekst i alle svar (ellers maskeret: `+45••••••50`, `m•••@firma.dk`) | staff |
| `webhooks:manage` | `…/webhooks` (CRUD, hændelser, leveringer) | admin |
| `bookings:write`, `knowledge:propose` | Reserveret (fase 3/5); kan gives, men ingen endpoints endnu | – |

Privat (personligt arbejdsrum, nøgle fra `POST /api/v1/privat/api-keys`): `tasks:read`, `tasks:write`, `calls:read`,
`calls:propose`, `reminders:write`. I fase 1–2 svarer en Privat-nøgle kun på `GET /v1/me`; ressourcerne under `/v1/me/…`
kommer i fase 3.

## Ressourcer (alle under `/v1/workspaces/{workspace_id}`)

| Metode og sti | Filtre | Bemærkning |
|---|---|---|
| `GET /me` (uden workspace) | | Nøglens arbejdsrum, navn, scopes |
| `GET /calls`, `GET /calls/{id}` | `since`, `until` (oprettet), `direction` | Uden `cost_usd_micros`, `provider_call_id`, `recording_url` |
| `GET /conversations`, `/conversations/{id}` | `channel` (webchat/phone), `status` | Sorteret efter seneste aktivitet |
| `GET /conversations/{id}/messages` | `limit` ≤ 500 | Ældste først; roller `visitor | assistant | staff` |
| `GET /booking-types` | `include_inactive` | |
| `GET /bookings`, `/bookings/{id}` | `from`, `to` (starttid), `status` | Uden kalender-id'er og `provider_call_id` |
| `GET /leads`, `/leads/{id}` | `since`, `pipeline_status`, `qualification_status` | Uden afregning (`billing_*`, `fee_snapshot`) |
| `GET /knowledge`, `/knowledge/{item_id}` | `kind` | Kun `approved` + `audience=public`; kladder ses aldrig |
| `GET /campaigns` | `status` | Kun kundekampagner, uden priser og budget |
| `GET /do-not-call` | | |
| `POST /do-not-call` `{phone, reason?}` | `Idempotency-Key` påkrævet | 201 ny / 200 fandtes; ventende kampagnekontakter med nummeret springes over. Kan ikke slettes via API |
| `GET /reports/daily`, `/reports/daily/{date}` | `from`, `to`, `limit` | Afsluttede dage; tal for samtaler, henvendelser og opgaver (ingen AI-omkostninger) |
| `GET /webhooks/events` | | Hændelsestyper med beskrivelse |
| `GET/POST /webhooks`, `GET/PATCH/DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries` | | Se *Webhooks* |

**Godkend-først.** Ingen offentlig rute sætter en status, godkender viden, afregner en henvendelse eller starter en kampagne.
Den eneste skrivning i v1 er ring-ikke-listen, som er sikker i sig selv (mindre kontakt, aldrig mere). Alt der skriver
domænedata, kommer i fase 3 som *forslag* (kladde/`proposed`) med `approval.requested`, og godkendes i appen.

## Pagination

Lister tager `?limit=` (1–200, standard 50) og `?cursor=`. Svaret er `{"items": [...], "next_cursor": "…" | null}`.
Cursoren er uigennemsigtig (keyset på oprettelsestid + id, nyeste først) og stabil, mens nye rækker kommer til.
Små lister (aftaletyper, viden, rapporter, webhooks, beskeder) svarer med `next_cursor: null`.

## Idempotency

`Idempotency-Key` (1–200 tegn, fx et UUID) er **påkrævet på POST**. Samme nøgle + samme body → det første svar gentages
(også status); samme nøgle + anden body → `409 idempotency_payload_mismatch`. Nøglerne er scopet pr. API-nøgle og rute
(`api:{key_id}:…`), så to systemer kan ikke kollidere. Hemmeligheder (webhook-secret) gentages aldrig i et replay.

## Rate limits

Pr. nøgle: **600 læsninger** (GET/HEAD/OPTIONS) og **60 skrivninger** pr. minut (token bucket, burst op til grænsen).
`X-RateLimit-Limit` og `X-RateLimit-Remaining` er på hvert svar; ved `429` også `Retry-After` (sekunder). Grænsen
håndhæves pr. proces (`app/modules/public_api/ratelimit.py`, `LIMITER`); et delt Redis-backend kan erstatte den uden
ændringer i ruterne. Tal: `PUBLIC_API_READ_RPM`, `PUBLIC_API_WRITE_RPM`.

## Webhooks

```http
POST /v1/workspaces/{id}/webhooks
Idempotency-Key: 5f1c…
{"url": "https://crm.firma.dk/dialogbot", "events": ["call.completed", "lead.created"], "description": "CRM"}
→ 201 {"id": "…", "secret": "whsec_…", "events": [...], "active": true, ...}
```

`secret` vises kun i dette svar (lagres krypteret med `CREDENTIALS_KEY`). Adressen skal være offentlig https på
standardporten (samme regler som appens Zapier/Make-connector: ingen private adresser, ingen redirects følges).
Højst 10 endpoints pr. arbejdsrum.

**Hændelser** (`GET …/webhooks/events`): `call.completed`, `booking.created`, `booking.cancelled`, `lead.created`,
`conversation.ended`, `knowledge.version_approved`. Fase 3 tilføjer `task.done` og `approval.requested`.

**Payload** (`Content-Type: application/json`):

```json
{"id": "evt_3f2a…", "type": "call.completed", "created_at": "2026-11-07T09:12:30+00:00",
 "workspace_id": "…", "data": {"call_id": "…", "direction": "inbound", "from_number": "+4520304050",
 "to_number": "+4570123456", "started_at": "…", "ended_at": "…", "duration_seconds": 150,
 "ended_reason": "customer-ended-call", "summary": "Kunden vil …", "conversation_id": "…"}}
```

`id` er deterministisk pr. hændelse: samme `id` på hvert endpoint og hvert genforsøg → brug det til at afvise dubletter.
`data` for `lead.created`/`booking.*` har samme felter som Zapier/Make-connectoren (kontaktdata i klartekst – se *GDPR*).

**Levering.** Fra outbox-workeren (`public_webhook.deliver`, én hændelse pr. endpoint, skrevet i samme transaktion som
domæneændringen): `POST` med 10 s timeout. 2xx = leveret. 5xx, 429, timeout og netværksfejl genforsøges med eksponentiel
backoff (2, 4, 8 … op til 300 s) op til `WORKER_MAX_ATTEMPTS` (5); andre 4xx er endelige. Hver fejlet levering tæller
`failure_count` op (nulstilles ved succes); ved `PUBLIC_API_WEBHOOK_DISABLE_AFTER` (20) fejl i træk sættes endpointet
`active: false` med `disabled_reason`, og nye hændelser køes ikke til det. Genaktivér med `PATCH …/webhooks/{id}
{"active": true}`. `GET …/webhooks/{id}/deliveries` viser de seneste 50 forsøg (status, forsøg, fejl) – der er ingen
separat leveringstabel; outboxen *er* historikken.

**Signatur.** Header `Dialogbot-Signature: t=<unix-sekunder>,v1=<hex HMAC-SHA256>` over strengen `"<t>." + rå body`.
Afvis, hvis `|now − t| > 300 s` (replay-beskyttelse), og sammenlign i konstant tid.

Python:

```python
import hashlib, hmac, time

def verify(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        ts = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))

# Flask/FastAPI: verify(SECRET, request.get_data() / await request.body(), request.headers["Dialogbot-Signature"])
```

Node:

```js
const crypto = require("node:crypto");

function verify(secret, rawBody, header, tolerance = 300) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  const ts = Number(parts.t);
  if (!Number.isInteger(ts) || Math.abs(Date.now() / 1000 - ts) > tolerance) return false;
  const expected = crypto.createHmac("sha256", secret).update(`${ts}.`).update(rawBody).digest("hex");
  const given = Buffer.from(parts.v1 || "", "hex");
  return given.length === 32 && crypto.timingSafeEqual(Buffer.from(expected, "hex"), given);
}

// Express: app.post("/dialogbot", express.raw({ type: "application/json" }), (req, res) => {
//   if (!verify(SECRET, req.body, req.get("Dialogbot-Signature"))) return res.sendStatus(401);
//   res.sendStatus(204); });
```

Svar hurtigt (2xx) og behandl asynkront – efter 10 s regnes leveringen som fejlet.

## Versionering

* `/v1` er stabil: felter **tilføjes**, men omdøbes eller fjernes aldrig; nye hændelsestyper og scopes kan komme til.
  Et brud bliver `/v2` ved siden af, med mindst 6 måneders overlap.
* `docs/public-openapi.json` er kontrakten og er versioneret i git; CI fejler, hvis koden og filen afviger.
* Deprecations annonceres i changelog'en på developers.dialogbot.app og med `Deprecation`-/`Sunset`-headere.

## Drift

* Egen Render-tjeneste `dialogbot-public-api` (`infra/render.yaml`) fra samme kode med `APP_SURFACE=public`: kun `/v1`
  og `/health` er monteret – ingen sessioner, ingen Stripe/Vapi/Twilio-hemmeligheder i processen. Levering af webhooks
  sker i den eksisterende worker. `APP_SURFACE=internal` på den interne tjeneste, når DNS er skiftet; `all` (standard)
  i dev og tests.
* DNS: `api.dialogbot.app` → `dialogbot-public-api` (CNAME til Render). Den interne API beholder `api.dialogbot.dk`.
  Tjenesten kører i Frankfurt mod samme Supabase-database (`docs/environments.md`).
* Miljø: `APP_SURFACE`, `PUBLIC_API_BASE_URL`, `PUBLIC_API_READ_RPM`, `PUBLIC_API_WRITE_RPM`,
  `PUBLIC_API_WEBHOOK_DISABLE_AFTER`, `CREDENTIALS_KEY` (samme værdi som workeren).

## Sikkerhed og GDPR

* **Dataminimering:** svarene udelader omkostninger, leverandør-id'er, optagelser (`recording_url` er ikke med i v1;
  åbent spørgsmål 4 i forslaget) og afregningsfelter. Telefonnumre og e-mails er maskeret uden `contacts:read`.
* **Godkend-først:** ingen offentlig rute kan godkende eller sætte en status (se ovenfor). Skrivninger via API logges i
  revisionsloggen med `api_key_id`.
* **Nøgler:** kun digest gemmes; udstedelse/tilbagekaldelse er audit-logget; udløb valgfrit; to aktive pr. arbejdsrum.
* **Webhooks med persondata:** modtageren (CRM, Zapier …) er selvstændig dataansvarlig for det, de modtager. Vilkårene for
  API-partnere skal have en databehandleraftale (DPA) som bilag, og kunden accepterer dem, når nøglen udstedes
  (UI-tekst i appen – ikke en del af dette repo). Data forlader ikke EU fra vores side (Render Frankfurt, Supabase
  eu-central-1), men kundens modtager kan ligge hvor som helst.
* **Privat:** nøgler er personlige og bundet til det personlige arbejdsrum; ingen adgang til andre medlemmers lister.

## Næste faser (ikke med her)

Fase 3: Privat-ressourcer (`/v1/me/tasks`, reminders, `calls/propose`, `apps/{key}/data`), `approval.requested`,
knowledge-drafts. Fase 4: OAuth2 client credentials + MCP-server. Fase 5: TypeScript-SDK og `POST bookings`.
