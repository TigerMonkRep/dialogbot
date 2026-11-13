# Cold outreach – compliant B2B e-mail for Dialogbot's own sales

Version 1 · 12 November 2026 · code in `app/modules/outreach/` · **off by default** (`OUTREACH_MODE=off`)

A deterministic `ComplianceEngine` decides what may happen to every lead **before** any Claude call, any lookup and
any send. Five agents then source, research, write, audit and dispatch one short plain-text e-mail whose only call to
action is the 90-second callback demo at `https://dialogbot.app`. No meeting is pushed, no SMS, DM or AI voice call is
ever made to a scraped contact, and nothing is sent unless an operator runs the dispatch step in `live` mode.

Not legal advice. Have the market matrix confirmed by a lawyer before the first live send.

## 1. Run a dry run for US and UK leads

A dry run does everything except send: compliance, research, copy, audit, queueing and (with `--render`) the final
rendering with the real unsubscribe link.

```bash
# 1. a migrated database
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/dialogbot
alembic upgrade head

# 2a. with Claude (real research and copy, costs tokens, sends nothing)
export ANTHROPIC_API_KEY=sk-ant-...
python -m scripts.outreach_dry_run app/modules/outreach/data/sample_leads.csv --countries US,UK --render

# 2b. offline, no key, no tokens (deterministic stand-in for Claude; dev/test only)
python -m scripts.outreach_dry_run app/modules/outreach/data/sample_leads.csv --countries US,UK --fake-ai --skip-mx --render
```

The script forces `OUTREACH_MODE=dry_run`; it cannot send whatever the environment says. Add `DK,DE,ES` to
`--countries` to see the call list, a hard block and a held market in the same run.

**Inspect the output.** The summary on screen shows, per lead, the status, the block reasons or the audited e-mail with
its footer. The JSON report (`outreach-<batch>.json`, or `--out`) holds everything:

| Field | What it tells you |
|---|---|
| `totals` | leads per status (`queued`, `blocked`, `held`, `call_queue`, `low_confidence`, `audit_failed`, …) |
| `leads[].compliance` | the engine's decision: `action`, `reasons`, the regime and the rule-set version |
| `leads[].hook`, `confidence` | the research agent's opener and its confidence after evidence checking |
| `leads[].email_draft` | `subject`, `body`, `footer`, `words`, `status`, and `rendered` (final text, with `--render`) |
| `leads[].email_draft.audit` | `passed`, every `issues` line, and the Haiku auditor's own verdict under `model` |
| `leads[].tokens`, `tokens` | Claude tokens per lead and for the batch |

The same data is in the database (`outreach_leads`, `outreach_messages`, `outreach_logs`) and behind the operator API:
`POST /api/v1/operator/outreach/batches` (JSON leads or CSV text, max 50), `GET …/batches/{name}`,
`POST …/dispatch`, `GET …/call-queue.csv`, `POST …/suppressions`. All of them answer 501 while `OUTREACH_MODE=off`.

**CSV columns:** `company_name, email, country` (required) and `city, niche, website, phone, registration_number,
email_source, email_source_url, context`. `context` is free text for the research agent (website text, review
snippets). `email_source=published_website` plus `email_source_url` is required for CA and AU. Rows exported from
Outscraper/Apify can be mapped with `agents/sourcing.from_scraper_rows()`.

## 1b. The admin tab: Admin → «Kold e-mail» (`/app/operator/outreach`)

Operator-only, Danish. Everything above without a terminal:

- **Start en kampagne** – pick a country (only e-mail markets can be chosen), a city and a category; «Find virksomheder»
  searches Google Places (`GOOGLE_PLACES_API_KEY`) and reads the e-mail address each business publishes on its own
  website (`finder.py`, through `app/core/safe_fetch`). Tick the ones to use, name the campaign, and the leads are
  checked (one request, no AI) and then researched, written and audited one lead per request. A pasted CSV works too.
- **Kampagner** – every lead's status, block reasons, confidence, the e-mail and the audit's objections. In dry run
  «Gør e-mails færdige» renders them with the real unsubscribe link; in live «Send køen nu» asks once more, then sends.
- **Inden du går live** – the to-do list (`readiness.py`). Automatic points follow the configuration (mode, Claude,
  demo countries, postal address, inboxes, provider, webhooks, billable prices); three manual points (lawyer, sending
  domain DNS, dry run read) are ticked by hand and stored in `outreach_todo_marks`.
- **Ringeliste (Danmark)** and **Landeregler** – the call-list download and the matrix in plain words.

API behind it: `GET …/overview` (answers also while off), `POST …/search`, `POST …/batches` with `research: false`,
`POST …/batches/{name}/process?limit=1`, `PUT …/todos/{key}`.

## 2. Market matrix (`compliance/matrix.py`)

| Market | Decision | Extra rules enforced in code |
|---|---|---|
| US | e-mail | CAN-SPAM footer: commercial message, sender, postal address, one-click unsubscribe |
| UK | e-mail | corporate subscribers only: name must end in Ltd/Limited/LLP/PLC; webmail rejected |
| IE | e-mail | webmail rejected; legitimate-interest footer |
| CA | e-mail | only when the business itself published the address (`email_source_url`); CASL footer |
| AU | e-mail | same publication rule; sender ID + unsubscribe |
| SE, FR | e-mail | webmail rejected; legitimate-interest footer |
| NO | e-mail | generic company addresses only (`post@`, `info@`, …); webmail rejected |
| **ES, PL** | **hold** | nothing happens until listed in `OUTREACH_SIGNED_OFF_MARKETS` |
| DK | call list | no e-mail/SMS/DM. ApS or A/S with a CVR number → `outreach_human_call_queue` after the CVR *reklamebeskyttelse* check |
| DE, AT, NL, IT, CH, BE | block | dropped; never e-mailed, never queued for calls |
| anything else | block | an unknown market is never «allowed» |

Channel guardrail: the engine refuses `sms`, `dm`, `ai_voice`, `voice` and `whatsapp` for every market. AI voice
calls only happen when a prospect enters their own number on dialogbot.app (the existing demo flow).

### Where this differs from the brief of 12 November – on purpose

1. **Poland and Spain are on hold, not approved.** Poland's Electronic Communications Law (art. 398, in force
   10 November 2024) requires prior consent for commercial e-mail and applies to business recipients too. Spain's
   LSSI art. 21 makes prior consent the main rule and published guidance disagrees on any B2B exception. Enable either
   with `OUTREACH_SIGNED_OFF_MARKETS=ES,PL` once a lawyer has confirmed.
2. **Only Denmark feeds the call list.** Cold-calling rules differ per country (Germany, for one, restricts B2B
   calls), so other blocked markets are dropped. `OUTREACH_CALL_QUEUE_COUNTRIES` exists, but only DK has scrub rules.
3. **CVR, not Robinson, for Danish companies.** The Robinson list covers private persons; a company is checked against
   *reklamebeskyttelse* in the CVR register (`app/modules/business/cvr.py`). Without `CVR_USERNAME`/`CVR_PASSWORD` the
   row is queued as `needs_review` and left out of the default export.
4. **Table names** carry an `outreach_` prefix (`outreach_leads`, `outreach_logs`, `outreach_suppression_list`,
   `outreach_human_call_queue`, plus `outreach_messages`) because `leads` already is the customers' lead table. The
   suppression list is a PostgreSQL table, not a separate `suppression_list.db` file, so it is shared by every process.
5. **Instantly and Smartlead are not wired.** `resend` and `smtp` are implemented; the other two names are reserved
   and refuse to start in live mode instead of pretending to send.

## 3. Before `OUTREACH_MODE=live` – open points

| # | Point | Why it blocks | Where |
|---|---|---|---|
| 1 | **The callback demo only rings Danish numbers today** (`DK_NUMBER` in `sales/service.py`), in Danish, with a script aimed at 3–4 minutes (`MAX_SECONDS = 420`) | The e-mail promises a 90-second demo call in the reader's market; for a US or UK reader the form rejects the number. Live sending to a country waits until it is listed in `OUTREACH_DEMO_CALLBACK_COUNTRIES` | demo flow + Twilio numbers |
| 2 | Full postal address | CAN-SPAM and CASL ask for a valid physical postal address; «Aarhus, Denmark» is not one. Live mode refuses to start without `OUTREACH_POSTAL_ADDRESS` | env |
| 3 | GBP price | USD is a billing currency since 13 November 2026 (`billing/markets.py`: $349/mo; US leads are sent to `dialogbot.app/us`). GBP is not: a UK company is billed in EUR, so `£275/mo` (`OUTREACH_PRICE_UK`) is a display value – add the currency or change the copy before quoting it | billing |
| 4 | Local callback numbers | The copy may only mention a `+1`/`+44` number when `OUTREACH_CALLBACK_NUMBER_US/UK` is set | Twilio |
| 5 | Sending domain | Use a separate, warmed-up domain with SPF, DKIM and DMARC; list its inboxes in `OUTREACH_SENDER_INBOXES` | DNS |
| 6 | Webhooks | Resend: the one webhook on `POST /api/v1/webhooks/resend` (`RESEND_WEBHOOK_SECRET`) with `email.received`, `email.bounced` and `email.complained` switched on, and receiving enabled on the inbox domain. Other senders: `POST /api/v1/webhooks/events` with `OUTREACH_WEBHOOK_SECRET` in `X-Outreach-Secret` | provider |
| 6a | Replies reach a person | `OUTREACH_REPLY_FORWARD_TO`: a copy of every reply to an outreach inbox is sent there (the inbox has no mailbox; `outreach/replies.py`). Needs a Resend key on the API service | Render |
| 6b | Demo line | `OUTREACH_DEMO_LINE_US/UK`: a local number Dialogbot's own assistant answers. Set = the e-mail invites the reader to ring it (nobody is rung, so no consent question and no SMS code) and the market counts as having a demo. The number is added to the sales workspace with «Tilknyt nummer fra Twilio» (operator → Telefoni), and English must be on in that workspace's languages | Twilio, Render |
| 7 | Legal review | The matrix, the footers, the privacy notice (GDPR art. 14) and a documented legitimate-interest assessment | lawyer |
| 8 | Models | Defaults are the brief's `claude-sonnet-4-6` / `claude-haiku-4-5`; change with `CLAUDE_*_MODEL` if you run newer ones | env |

Sending never runs on a schedule: `POST /operator/outreach/dispatch` (operator only) is the one way out.

## 4. The agents (`app/modules/outreach/agents/`)

| Agent | Model | What it does | Rejects when |
|---|---|---|---|
| `LeadSourcingAndQualificationAgent` | none | CSV / scraper rows → ComplianceEngine → niche filter (plumber, HVAC, dentist, med spa, auto repair, hair salon) → MX lookup; DK → CVR scrub → call list | blocked/held market, webmail where not allowed, unknown niche, no MX |
| `PainPointResearchAgent` | `CLAUDE_RESEARCH_MODEL` + web search | `LeadBrief`: call handling, verbatim review snippets, ticket value, `personalization_hook`, `confidence_score` | not a business; `confidence_score < 0.6`. A quote not found in the supplied material is dropped, and a brief without evidence is capped at 0.4 |
| `OutreachCopywriterAgent` | `CLAUDE_WRITER_MODEL` | three lines (observation · what Dialogbot does · callback demo), localized price and spelling. The footer is appended by code, never written by the model | – |
| `ComplianceAndSafetyAuditorAgent` | rules, then `CLAUDE_AUDITOR_MODEL` | market + suppression again, < 90 words, exact footer with `{{unsubscribe_link}}`, no B2C wording or «Peter», no generic opener, no meeting push, only dialogbot.app links, configured price/number only, plain text, honest subject; then an adversarial read of every claim against the evidence; then daily limits | any issue. Haiku is only called when the rules pass |
| `DispatcherAndWebhookHandler` | none | re-checks the engine at send time, renders the signed unsubscribe link and `List-Unsubscribe` one-click headers, sends via Resend or SMTP; `/unsubscribe` and `/webhooks/events` write to the suppression list at once and cancel everything pending. A reply halts the sequence; a bounce or complaint also suppresses | suppressed since the audit, limits reached, demo not available in the country |

Claude is called through the official `anthropic` SDK (`llm.py`): forced tool use with the pydantic model's JSON
schema as structured output, one corrective retry on a schema error, the SDK's own exponential backoff on 429/5xx
(`OUTREACH_AI_MAX_RETRIES`), and one `outreach_logs` row (`kind=llm_usage`) with tokens, model and latency per call.
`llm.structured()` takes a `Clearance` that only an `EMAIL` decision of the engine can issue – that is the mechanism
that keeps blocked leads from costing tokens.

Only step 1 of a sequence is written today. Follow-up e-mails are not generated; the halt logic (`suppression.halt`)
already covers every later step.

## 5. Tests

`tests/test_outreach_compliance.py`, `test_outreach_pipeline.py`, `test_outreach_dispatch.py` (Anthropic mocked, real
PostgreSQL). They prove, among other things:

- DK, DE, NL, AT, IT (and CH, BE) leads never reach Claude: zero model calls, zero token rows, no e-mail; DK goes to
  the call list only as ApS/A/S with a clean CVR.
- Any `@gmail.com` (yahoo, hotmail, outlook) lead in the UK is rejected, as is a UK sole trader or partnership.
- An unsubscribed address is refused by the engine, skipped by a new batch and cancelled at send time even if it is
  already queued.
- Passing e-mails carry the right footer per market, are under 90 words, contain the demo link and no B2C wording.
- Live mode refuses to start half-configured, and `off` is the default.

```bash
pytest tests/test_outreach_compliance.py tests/test_outreach_pipeline.py tests/test_outreach_dispatch.py
```
