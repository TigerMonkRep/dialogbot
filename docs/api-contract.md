# API-kontrakt — etape 1

Maskinlæsbar kontrakt: `docs/openapi.json` (eksporteres med `python -m scripts.export_openapi`; CI fejler ved drift). Interaktiv: `/api/v1/docs`.

## Generelt

- Base: `/api/v1`. Autentifikation: `Authorization: Bearer <access_token>` fra `POST /auth/login`.
- Fejl: `{ "code": string, "message": string (dansk), "field_errors": [{field, message?}], "request_id": string }` plus evt. ekstra felter (`current_version`, `required_role`, `capability`).
- `X-Request-ID` sendes/ekkoes i alle svar; logs er JSON med samme id. Tokens logges aldrig.
- Statusregler: `401` uautentificeret/ugyldig session, `403` manglende rettighed (`insufficient_role`, `role_escalation`, `email_not_verified`, `invitation_email_mismatch`), `404` ukendt **eller fremmed** objekt/arbejdsrum, `409` konflikt (`version_conflict`, `idempotency_payload_mismatch`, `last_owner`, `draft_exists`, `version_not_editable`, `invalid_transition`, `invitation_used|revoked|expired`, `task_required`, `email_taken`, `category_exists`), `422` validering, `501` bevidst ikke implementeret (`not_implemented`).
- Lister: `?limit=&offset=` → `{items, total, limit, offset}` (audit, vidensemner).
- Idempotens: `Idempotency-Key`-header på `POST …/invitations` og `POST …/versions/{id}/approve`. Scope er bruger + arbejdsrum + endpoint.
- Versionering: `profile`, `goals`, `languages` bærer `version`; `PUT` kræver `expected_version`. Kladder bærer `edit_version`; `PUT /knowledge/versions/{id}` kræver `expected_edit_version`.

## Konto (A01–A04, S08)

| Metode og sti | Beskrivelse | Tilstande |
|---|---|---|
| `POST /auth/register` | Opret konto; `signup_intent` (reception/campaigns/both) bevares (A01). Udløser simuleret bekræftelsesmail via outbox. | pending |
| `POST /auth/verify-email` `{token}` | Bekræft adresse; engangstoken med udløb. | verified / `token_invalid` / `token_expired` |
| `POST /auth/verify-email/resend` | Nyt token (kræver login). | |
| `POST /auth/login` | Returnerer `access_token` + bruger. Forkerte oplysninger giver altid `401 invalid_credentials`. | |
| `POST /auth/logout` | Tilbagekalder sessionen. | |
| `GET /auth/me` | Bruger inkl. `email_verified`. | |
| `POST /auth/password/forgot` `{email}` | Svarer altid `202` (ingen kontoenumerering). | |
| `POST /auth/password/reset` `{token,password}` | Ny adgangskode; alle sessioner tilbagekaldes; token single-use. | |
| `GET /auth/sessions` | Aktive sessioner (S08). | |

## Arbejdsrum, medlemmer, invitationer (A05, A06, S02, S09)

| Metode og sti | Beskrivelse |
|---|---|
| `POST /workspaces` `{name, product_intent?}` | Kræver bekræftet e-mail. Opretter ejer-medlemskab, profil, mål (med intent) og sprog. |
| `GET /workspaces` | Kun kalderens arbejdsrum med rolle. |
| `GET /workspaces/{id}` | |
| `GET /workspaces/{id}/members` | |
| `PUT …/members/{mid}/role` `{role}` | Ingen eskalering over egen rolle; ejerrolle kun af ejer; sidste ejer beskyttet (`409 last_owner`). |
| `DELETE …/members/{mid}` | Fjern (admin+) eller forlad selv; sidste ejer beskyttet. |
| `GET/POST …/invitations` | Opret (admin+; rolle ≤ egen; admin/staff/reader). Eksisterende afventende invitation returneres med `200` i stedet for dublet. Token kun i (simuleret) mail. |
| `POST …/invitations/{iid}/revoke` / `/resend` | Resend udsteder nyt token (rå token gemmes aldrig). |
| `GET /invitations/{token}` | Offentlig forhåndsvisning: arbejdsrumsnavn, e-mail, rolle, status (pending/expired/revoked/accepted). |
| `POST /invitations/accept` `{token}` | Kræver login med samme e-mail. Single-use. Opretter medlemskab i **det** arbejdsrum; aldrig arbejdsrum/abonnement. |
| `GET …/audit?limit&offset` | Læsbar historik (admin+): aktør, handling, objekt, før/efter, request_id. |

## Virksomhed (O01, O03, O04, S01)

| Metode og sti | Felter |
|---|---|
| `GET/PUT …/profile` | `legal_name, description, website_url?, manual_setup, cvr?, address_line?, postal_code?, city?, country, timezone, phone?, version` |
| `GET …/categories/suggested` | Startforslag; ikke en begrænsning. |
| `GET/POST …/categories`, `DELETE …/categories/{cid}` | `label, slug?, is_primary`; egne kategorier får `is_custom=true`. |
| `GET/PUT …/goals` | `product_intent, guidance_mode (guided/self_managed), inbound_phone, webchat, callback, booking, conversation_goals[]` |
| `GET/PUT …/languages` | `interface_language, default_conversation_language, enabled_conversation_languages[], report_language` (standard skal være aktiveret). |

Enhver ændring skriver audit og markerer afhængige tjek forældede.

## Viden (K01, K03, K04, K05, O02)

Arter: `fact, service, coverage_area, opening_hours, known_answer, unknown_answer, offer`. Versionstilstande: `draft → in_review → approved → superseded`; `rejected`.

| Metode og sti | Beskrivelse |
|---|---|
| `GET …/knowledge/items?kind=` | Emner med `approved_version` og `open_draft`. |
| `POST …/knowledge/items` | Nyt emne + kladde v1 (staff+). |
| `GET …/knowledge/items/{iid}`, `GET …/versions` | Emne / versionshistorik. |
| `POST …/knowledge/items/{iid}/drafts` | Ny kladde af eksisterende emne; den godkendte version røres ikke; kun én åben kladde. |
| `PUT …/knowledge/versions/{vid}` | Redigér kladde (`expected_edit_version`); godkendte versioner kan ikke redigeres in-place. |
| `POST …/versions/{vid}/submit` | draft → in_review. |
| `POST …/versions/{vid}/approve` | admin+; idempotent; superseder tidligere godkendt; bumper `knowledge_revision`; outbox `knowledge.version_approved`; forælder vidensafhængige tjek. |
| `POST …/versions/{vid}/reject` `{reason}` | admin+. |
| `GET …/knowledge/review-queue` | Versioner i gennemgang. |
| `GET …/assistant/knowledge` | **Kun godkendte** aktuelle versioner + `knowledge_revision`. AI-samtalen er ikke implementeret. |
| `GET …/knowledge/offers/{iid}/eligibility?area_m2&on_date` | Evaluerer den godkendte version af et `offer` (K04: `gte 40`, datoer inklusive). |

`offer.content`: `{discount_percent, condition:{area_operator: gte|gt|lte|lt, area_threshold_m2}, starts_on, ends_on_inclusive}`.

## Opsætningsplan (G01–G08)

| Metode og sti | Beskrivelse |
|---|---|
| `GET …/setup/plan` | Serverberegnet: `progress {required_total, required_complete, percent, estimated_minutes_remaining}`, `next_action`, `next_action_explanation`, `blocked_required[]`, `resume {open_drafts, in_review, last_activity_at}`, `tasks[]`, `checks[]`. |
| `GET …/setup/tasks/{key}` | Én opgave: `status ∈ complete, in_progress, not_started, blocked, skipped, not_available`; `required`; `blocked_by[] {type: capability|dependency|permission, message}`; `destination` (kanonisk frontendrute); `requirement_ids`; `you_can_act`; `assigned_to`; `stale_checks`. |
| `POST …/setup/tasks/{key}/skip` / `/unskip` | Kun valgfrie trin (`409 task_required`). |
| `PUT …/setup/tasks/{key}/assignee` `{user_id}` | G07; modtager skal være medlem; kun admin+ kan tildele andre. |
| `POST …/setup/checks/{key}/run` | Kører et servertjek; ikke-implementeret kapabilitet → `501`, intet registreres. |
| `POST …/setup/checks/run-all` | Kører alle kørbare; `skipped[]` med begrundelse. |
| `GET …/setup/checks/history` | Resultater med scope, miljø, `config_versions`, `evidence`, `stale_reason`. |
| `POST …/setup/activate/reception`, `/campaigns` | Særskilte kommandoer (admin+). Svarer `501` i denne etape. Betaling, publicering og lancering er andre kommandoer. |

Opgavekatalog (`app/modules/setup/plan.py::TASKS`): `business.profile`, `business.categories`, `goals.select`, `languages.settings`, `knowledge.services`, `knowledge.opening_hours` (valgfri for kampagne-only), `knowledge.coverage_area` (valgfri), `knowledge.answers` (valgfri), `knowledge.review` (admin), `checks.server`, `reception.telephony_forwarding`*, `reception.test_call`*, `reception.webchat`*, `booking.calendar`*, `campaign.first`*, `activation.reception`*, `activation.campaigns`*. `*` = `not_available` i etape 1.

Tjek (`checks.py::CHECKS`): `profile.completeness`, `languages.consistency`, `knowledge.approved_coverage`, `knowledge.assistant_endpoint` (kørbare); `telephony.test_call`, `telephony.forwarding`, `calendar.connection`, `webchat.widget`, `campaign.test_call` (kræver ikke-implementerede adaptere).

## Ambassadører

Se `docs/ambassadors/program.md` for regler.

| Metode og sti | Beskrivelse |
|---|---|
| `GET /public/ambassadors/program` | Vilkår, regeltekst og quiz (uden svar). Offentlig. |
| `GET /public/ambassadors/{slug_or_code}` | Offentlige data for en aktiv ambassadør (fornavn, hilsen, kode, kunderabat). Ellers 404. |
| `POST /public/ambassadors/{slug_or_code}/visit` | Tæller et besøg pr. dag (aggregeret, uden IP). 204, også ved ukendt ref. |
| `GET /public/ambassadors/parent-consent/{token}`, `POST /public/ambassadors/parent-consent` | Forældregodkendelse fra mail-linket (`{token, parent_name, confirm:true}`). |
| `GET /ambassador/me` | `{enrolled:false}` eller profil: status, link, kode, vilkår, saldi (`held/payable/in_payout/paid`), statistik, `payout_blockers`. CPR og bank vises kun som `has_cpr`/`bank_last4`. |
| `POST /ambassador/apply` | Tilmelding: `kind` (`private` → `birth_date`, evt. `cpr`, forælder under 18; `company` → `cvr`), evt. bank, `rules_version`, `quiz`. `422 rules_quiz_failed` (+`wrong`), `too_young`, `rules_outdated`; `409 already_ambassador`. |
| `PUT /ambassador/me` | CPR, bank, hilsen, telefon; `expected_version` → `409 version_conflict`. |
| `POST /ambassador/me/parent-consent/resend` | Send forældremail igen. |
| `GET /ambassador/me/customers`, `/ledger`, `/payouts`, `/payouts/{id}` | Kunder (firmanavn, status, periode, bonus), posteringer, udbetalinger og afregningsbilag. |
| `GET/PUT /workspaces/{ws}/referral` | Kundens ambassadør (billing.read); tilføj kode (billing.manage) inden for 30 dage og før første faktura: `unknown_code`, `self_referral`, `already_referred`, `code_window_closed`. |
| `POST /workspaces` | Har nu også `referral_code` og `referral_link`. Ugyldige refs ignoreres. |
| `GET /operator/ambassadors` | Operatør. Liste med saldi og totaler (`?status=`). |
| `GET /operator/ambassadors/{id}` | Detaljer inkl. kunder, posteringer, udbetalinger. |
| `POST /operator/ambassadors/{id}/approve \| reject \| suspend \| reactivate` | `{note}`; mail ved godkend/afvis. `409 invalid_transition`. |
| `PUT /operator/ambassadors/{id}/terms` | `{bonus_minor, rate_bp, months, expected_version}`. |
| `POST /operator/ambassadors/{id}/reveal` | CPR og bank i klartekst (logges). |
| `PUT /operator/ambassadors/referrals/{workspace_id}` | Flyt/fjern kundens ambassadør `{ambassador_id\|null, reason}` (logges). |
| `GET/POST /operator/ambassadors/payouts`, `GET /operator/ambassadors/payouts/{id}`, `POST …/{id}/paid` `{reference}`, `POST …/{id}/cancel` | Udbetalingskørsler (≥ 500 kr., kun uden blokeringer). |
| `GET /operator/ambassadors/b-income.csv?year=` | Udbetalt B-indkomst pr. privat ambassadør (navn, CPR, beløb) til eIndkomst. Logges. |

## Integrationer, drift, dev

| Metode og sti | Beskrivelse |
|---|---|
| `GET /integrations/capabilities` | Ærlig status pr. adapter: `available | simulated | not_implemented`. |
| `GET /workspaces/{ws}/integrations` | Katalog over connectors med status pr. arbejdsrum (`not_connected | connected | error | not_implemented`), begrundelse, deklarerede handlinger (navn, dansk beskrivelse, JSON-schema, `confirm`), hændelser, `simulated` og de seneste 20 `action_runs`. Hemmeligheder returneres aldrig. Staff+. |
| `POST /workspaces/{ws}/integrations/{key}/connect` | Admin+. `Idempotency-Key`. Body `{config, secrets}`. OAuth (`google_calendar`, `microsoft_calendar`): `{status:"authorize", authorize_url}` (PKCE S256 + engangs-`state`, 10 min). Webhook/Zapier/Make: tester adressen og svarer `{status:"connected", signing_secret}` – hemmeligheden vises kun her, også ikke ved genafspilning af samme nøgle. `bookings` → `409 connector_builtin`; ikke tilgængelig → `501 connector_not_available`; testkald fejler → `502 connection_test_failed`. |
| `GET /integrations/oauth/{key}/callback` | Leverandørens redirect (ingen login). Bytter koden med PKCE, tester forbindelsen og sender browseren til frontend med `?connected={key}` eller `?error={code}&connector={key}` (`oauth_state_unknown`, `oauth_state_expired`, `oauth_denied`, `oauth_failed`). |
| `PUT /workspaces/{ws}/integrations/{key}` | Admin+. Ikke-hemmelig opsætning `{config, expected_version}` → `409 version_conflict`. |
| `POST /workspaces/{ws}/integrations/{key}/test` | Admin+. `Idempotency-Key`. Rigtigt testkald; `{ok, facts | error, simulated}`. En fejl sætter connectoren til `error`. |
| `POST /workspaces/{ws}/integrations/{key}/run` | Admin+. Afprøv en handling (`{action, input}`); kører gennem samme validering og logges med kanal `test`. |
| `DELETE /workspaces/{ws}/integrations/{key}` | Admin+. Tilbagekalder OAuth-token (Google; best effort), sletter den krypterede hemmelighed. 204. |
| `GET /workspaces/{ws}/integrations/actions` | Staff+. `action_runs` (`?connector=`, `?limit=`). |
| `GET /workspaces/{ws}/conversations/{id}` | Har nu også `actions`: handlingerne i samtalen i tidsorden. |

**Handlinger i samtaler.** Telefonens `assistant-request` og webchatten får de samme funktionsværktøjer: alle handlinger fra connectors med status `connected` (et forbundet Google/Microsoft-kalender overtager bookinghandlingerne fra Dialogbots kalender). Input valideres mod schemaet (`additionalProperties:false`); handlinger med `confirm` kræver `bekraeftet:true`. Hvert kald giver én `action_runs`-række – også når det afvises eller fejler – og et resultat i tekst, modellen kan give videre. **Udgående hændelser** (`lead.created`, `booking.created`, `booking.cancelled`, `action.completed`, `conversation.ended`, `test.ping`) sendes via outboxen til forbundne webhook/Zapier/Make med `X-Dialogbot-Signature: t=<unix>,v1=<hex HMAC-SHA256 af "<t>.<body>">`; retry med backoff, og efter sidste forsøg vises fejlen på connectoren.
| `GET /health/live`, `GET /health/ready` | Ready tjekker database og at Alembic-head er anvendt. |
| `GET /dev/mailbox`, `GET /dev/outbox` | Kun med `ENABLE_DEV_TOOLS=true`; mailbox viser kun egne mails. Ikke en del af den committede kontrakt. |
