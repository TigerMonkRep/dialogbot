# Kravstatus — etape 1

Kun krav, der er berørt af denne etape, er opført. Statusniveauer: **implementeret (backend)**, **delvist**, **ikke implementeret**. "Testet" betyder integrationstest mod PostgreSQL i `tests/` og CI; intet er browserafprøvet eller udbyderverificeret. Frontendruter i kolonnen "Rute" er de kanoniske ruter fra kravmatricen, som en kommende frontend skal binde til backendens endpoints; der findes ingen frontend i repositoriet. Krav, der ikke nævnes (P*, W*, R*, I*, T*, BK*, C*, B*, E*, H*, M*, X*, S03–S07, S10, K02), er **ikke implementeret**.

| Krav | Rute | Status | Backend | Tests | Bemærkninger / rest |
|---|---|---|---|---|---|
| A01 Signup med bevaret produktintention | /signup | Implementeret | `identity/service.register`, `users.signup_intent` | `test_register_login_verify_logout` | Intent bæres videre til arbejdsrum (A06). |
| A02 Login, ugyldige oplysninger | /login | Implementeret | `identity/service.login` | `test_invalid_credentials_and_missing_auth` | "Husket destination" er frontendansvar. |
| A03 E-mailbekræftelse, resend, udløb | /verify-email | Implementeret | `auth_tokens(purpose=verify_email)`, `/auth/verify-email(/resend)` | `test_register_login_verify_logout` | Udløb testes indirekte via tokenregler (`_consume`); simuleret mail. |
| A04 Glemt/nulstil adgangskode | /password/* | Implementeret | `request_password_reset`, `reset_password` | `test_password_reset_flow` | Single-use, sessioner tilbagekaldes. |
| A05 Invitation via token | /invite/:token | Implementeret | `workspaces/service.accept_invitation`, `GET /invitations/{token}` | `test_invitation_single_use_*`, `test_expired_and_revoked_*` | Kræver login med matchende e-mail; udløbet/tilbagekaldt afvises; rigtigt arbejdsrum. |
| A06 Opret/vælg arbejdsrum, gem intent | /onboarding/workspace | Implementeret | `create_workspace`, `GET /workspaces` | `test_register_login_verify_logout`, `two_workspaces` | |
| O01 Virksomhedsoplysninger, manuel opsætning, flere/egne kategorier | /onboarding/business | Implementeret | `business/router` profile + categories | `test_manual_setup_without_url_*` | Dokumentupload/URL-crawl **ikke** implementeret (kun feltet `website_url`). |
| O02 Gennemgang af udtrukne fakta | /onboarding/knowledge | Delvist | Kun manuel viden via `knowledge`-modulet | `test_assistant_endpoint_*` | Udtræk/"unknowns" fra kilder er ikke implementeret; manuelle emner af arten `unknown_answer` findes. |
| O03 Mål, foreslåede spørgsmål, intent-grene | /onboarding/goals | Delvist | `goal_selections` (intent, kapabiliteter, `conversation_goals[]`) | `test_manual_setup_*`, `test_campaign_only_plan_*` | Foreslåede spørgsmål/intent-grene gemmes som data, fortolkes ikke. |
| O04 Fire sprogniveauer | /onboarding/languages | Implementeret (uden stemmeprøve) | `language_settings` | `test_manual_setup_*` | Stemmeprøve kræver AI/stemmeadapter (ikke implementeret). |
| O05 Assistentmanuskript, hilsen, fallback | /onboarding/assistant | Ikke implementeret | — | — | Etape 2. Godkendt viden er forudsætningen og findes. |
| O06 Simulerede testscenarier | /onboarding/test | Ikke implementeret | Planopgaven `reception.test_call` er `not_available` | `test_campaign_only_plan_*` | En simuleret test kan aldrig aktivere produktion (registret). |
| O07 Aktiveringsoversigt og personlig plan | /onboarding/activation | Delvist | `setup/plan` (readiness, næste trin pr. produkt) | `test_campaign_only_plan_*` | Aktiveringskommandoer findes men svarer `501`. |
| K01 Godkendte fakta, kilder, katalog, tilbud, kø | /app/knowledge | Delvist | `knowledge/router` (items, review-queue, assistant) | `test_assistant_endpoint_*` | Kilder (K02) findes ikke; `source_type` er altid `manual`. |
| K03 Ydelser, dækning, godkendte priser | /app/knowledge/catalogue | Delvist | Arter `service`, `coverage_area`; priser som `content` | `test_assistant_endpoint_*` | Ingen strukturel prismodel ud over `price_net_minor`/`currency` i indhold. |
| K04 Daterede tilbud med betingelser | /app/knowledge/offers | Implementeret (regel + editor-API) | `offer_is_eligible`, `validate_content`, `/offers/{id}/eligibility` | `test_offer_rule_k04_*` | DB-005 lukket: `gte 40`, 39/40/41 og 1. dec testet; kun godkendt version evalueres. |
| K05 Gennemgangskø | /app/knowledge/review | Delvist | `review-queue`, `submit/approve/reject` | `test_staff_cannot_approve_*`, `test_next_action_and_permission_*` | Konflikt-/kildeændringsdetektion kræver kilder (ikke implementeret). |
| S01 Virksomhedsprofil | /app/settings/business | Implementeret | som O01 | `test_manual_setup_*` | Åbningstider ligger i viden (`opening_hours`), ikke i profil. |
| S02 Team, invitationer, roller, fjern | /app/settings/team | Implementeret | `workspaces/router` members + invitations | `test_staff_cannot_*`, `test_admin_cannot_escalate_*`, invitationstests | Bekræftelsesdialog er frontend. |
| S08 Profil, sprog, sessioner, log ud | /app/settings/profile | Delvist (UI bygget, skrivebeskyttet) | `/auth/me`, `/auth/sessions`, logout, reset | `test_register_login_*`, `test_password_reset_flow` | Redigering af navn/brugerfladesprog via API mangler (kun ved oprettelse). |
| S09 Aktivitetslog | /app/settings/activity | Implementeret | `audit_log`, `GET …/audit` | `test_admin_cannot_escalate_*`, `test_config_change_*` | Kun admin+ kan læse. |
| G01 Opsætningshjem, én næste handling, ærlig fremdrift, gem/genoptag | /app/setup | Implementeret | `setup/plan.compute_plan` | `test_resume_after_new_session`, `test_required_task_cannot_be_skipped_*` | Reparationstilstande begrænset til `stale`-tjek. |
| G02 Mål/vejledningsvalg, redigérbar plan | /app/setup/plan | Delvist | `guidance_mode`, opgaver afledt af mål | `test_manual_setup_*`, `test_campaign_only_plan_*` | "Eksisterende værktøjer" som input findes ikke. |
| G03 Guidet wrapper om kanoniske editorer | /app/setup/tasks/:taskId | Delvist | `GET …/setup/tasks/{key}` (forklaring, destination, status, spring) | `test_required_task_*` | Eksempler/forhåndsvisning er frontend; API'et leverer `explanation` og `destination`. |
| G04 Kontekstuel hjælp | (drawer) | Delvist | `blocked_by[].message`, `you_can_act`, `min_role` | `test_next_action_and_permission_*` | Ingen forslag til rettelser/AI-forklaring. Omgår aldrig adgangskontrol (rettigheder håndhæves serverside). |
| G05 Målspecifikke tjek med evidens/tid/scope | /app/setup/readiness | Implementeret | `setup/checks.py`, `check_results` | `test_config_change_stales_dependent_checks_only` | Kun servertjek er kørbare; integrationstjek giver `501`. |
| G06 Aktiveringsgennemgang, særskilte handlinger | /app/setup/launch | Delvist | `POST …/activate/reception|campaigns` → `501` | `test_staff_cannot_*`, `test_campaign_only_plan_*` | Betaling/publicering/lancering er ikke implementeret; kontrakten holder dem adskilt. |
| G07 Opgaveejerskab/overdragelse | /app/setup/team | Implementeret | `PUT …/tasks/{key}/assignee` | `test_next_action_and_permission_*` | Bruger eksisterende invitationsflow. |
| G08 Første resultater, genåbnede tjek | /app/setup/next | Delvist | Genåbning: `stale`-tjek efter ændring | `test_config_change_*` | Ingen resultater/statistik (kræver reception). |
| P05 Prisberegner (regelgrundlag) | /pricing | Delvist (rene regler) | `billing/money.py` | `test_pricing_fixtures_model_a_and_b` | DB-001 forhindret i domænemodellen; intet endpoint. |
| B03/B04/M04 Tvist uden faktura (regelgrundlag) | — | Delvist (rene regler) | `decide_unbilled_dispute` | samme | DB-002 forhindret; ingen tvistmodel/endpoints. |

## Backlog-poster fra pakken, som denne etape adresserer

| ID | Status |
|---|---|
| DB-013 Tenant/rolle håndhæves på server og worker | Implementeret og testet (to-arbejdsrums-tests; worker arbejder kun via outbox-events knyttet til arbejdsrum). Operatørgrants (M02) ikke implementeret. |
| DB-014 Opsætning afledt af mål og evidens | Implementeret og testet (manuel rute uden URL, gem/genoptag, målafhængigheder, `stale` ved ændring, simulering aktiverer intet). |
| DB-017 Fælles fixtures og testur | Delvist: seed og tests bruger `canonical-demo-data.json`-værdier; K04 evalueres med eksplicit `on_date` (intet dagsdato-afhængigt). |
| DB-018 Ægte kapabilitet kan ikke udledes af demo | Implementeret via kapabilitetsregistret; alle adaptere ud over simuleret mail er `not_implemented`. |
| DB-001, DB-002, DB-005 | Reglerne er kodet og testet i backend; eksportens HTML er ikke rettet (ikke en del af etapen). |

## Design-verifikation mod Stitch (checkpoint 4)

Browserkontrolleret lokalt ved 1440 px (desktop-reference) og 390 px (mobil-reference) med `design-reference/tools/compare.mjs`: G01–G05, A06/O01/O02, K01–K05 (alle faner), A01–A05 (mobilreference), begge app-skaller. O03/O04 følger G01-kortdesignet (ingen egen Stitch-skærm). S02/S08/S09 og P01 er bygget i designsystemet (ingen egne Stitch-skærme). G03-wrapper mangler. E2E-rejser i `web/e2e` dækker A01–A06, O01–O04, K03–K05, G01/G05, S02/S08/S09 ved 1440 og 390 px. Se `docs/implementation-progress.md`, checkpoint 4.
