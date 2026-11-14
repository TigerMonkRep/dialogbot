E = "qa/evidence/VER1113B/"
v("F-AUD26-02", "closed",
  "Produktionen svarer read-only (GET https://dialogbot.app/api/backend/demo-call, 13/11 ca. 19:25) med `\"verification\":\"sms_code\"`. "
  "`tests/qa/test_qa_audit26_demo_call.py` (begge tests) og `tests/test_sales_demo_calls_sms_code.py` er grønne på kandidaten. "
  "P06-sms-kode.spec + P06.spec er grønne i 1440 + 390 (lokal stak, del af nabokørslen med 130 bestået, 0 fejl).",
  "ja. Hele a97fee5 kan ikke vendes på main, fordi verification.py er bygget videre i #222/#223. Derfor er tokenkravet fjernet målrettet "
  "(`verification.consume` i `POST /demo-call`). Det gav 2/2 røde i test_qa_audit26_demo_call.py "
  "(`test_one_client_rings_many_strangers_at_night`, `test_unproven_numbers_are_not_rung_in_bulk_at_night`) og 3 røde i test_sales_demo_calls_sms_code.py.",
  "P06, P06-sms-kode, S0-selvbetjening-24-7, A01-journey (1440 + 390). Fejlklassen er søgt i andre offentlige døre: /start-kvizzen, W04 og bookingformularen "
  "kræver kode. Webchat-assistentens `book_tid` gør ikke → ny F-VER1113B-02-W04 (S3).",
  "closed", "CLIENT_IP_SECRET på Render er ikke tjekket (kræver Fürster).")
v("F-HOT16-01", "closed",
  "`tests/test_sales_demo_calls_24_7.py` grøn. Prod read-only: /da/erhverv har 5 × «Opret dig» → /signup?intent=reception, og GET /demo-call "
  "har ingen open_now/hours. S0-selvbetjening-24-7.spec er grøn i 1440 + 390.",
  "ja (mutation, ikke revert: de to rettelser er bygget videre i a97fee5). Kaldevinduet 08–20 på hverdage er sat ind igen i `request_web`. "
  "Det gav 8 røde i test_sales_demo_calls_24_7.py (21:30, 03:00, søndag, søndag nat, 4 × gamle vinduesværdier).",
  "P06, P06-sms-kode, A01-journey, S0-selvbetjening-24-7 (1440 + 390)", "closed")
JE_NB = "A01-journey, A06, A02, A03, A04 (1440 + 390); tests/qa/test_qa_journey_erhverv.py + test_qa_journey_privat.py"
v("F-JE-01", "closed",
  "`test_F_JE_01_*` (2) og `tests/test_privat_verify_mail.py::test_privat_signup_can_still_create_a_business` er grønne. A06.spec er grøn i 1440 + 390.",
  "ja. Revert af d86a3f9 (app/) på main gav 3 røde (de to JE-01-tests + test_privat_signup_can_still_create_a_business).", JE_NB, "closed")
v("F-JE-02", "closed", "`test_F_JE_02_*` (2) grønne. A04.spec er grøn i 1440 + 390.",
  "ja. a25fdb0 kan ikke vendes helt på main (konflikt i privat_context.py/funnel). Derfor er der lavet en målrettet mutation `privat = False` i "
  "`request_password_reset`, og login/reset-siderne fra a25fdb0 er vendt. Resultat: test_F_JE_02 og test_F_JE_02b er røde.", JE_NB, "closed")
v("F-JE-03", "closed", "`test_F_JE_03` grøn. Adfærd: `privat_context.home` → /privat/dag for en ren Privat-konto.",
  "ja. Når login/page.tsx fra a25fdb0 vendes, bliver test_F_JE_03 rød. JE-03-testen læser kun kildekoden. Derfor er der også lavet en adfærdsmutation: "
  "`home()` → altid /app gør `test_qa_journey_privat.py::test_jp02_after_reset_a_privat_user_lands_in_privat` rød.", JE_NB, "closed")
v("F-JE-04", "closed", "`test_F_JE_04` grøn.",
  "ja. Mutationen `if kind == \"privat\"` → `if False` i funnel `_welcome` gør test_F_JE_04 rød.", JE_NB, "closed")
v("F-JE-05", "closed", "`test_F_JE_05` grøn.",
  "ja. Når `pctx.is_privat_user` fjernes fra `issue_verification`, bliver test_F_JE_05 rød.", JE_NB, "closed")
v("F-FIX18-01", "closed",
  "`tests/test_setup_and_knowledge.py::test_profile_website_written_as_bare_domain_is_saved_with_the_rest` er grøn. "
  "G-trin1-journey.spec (inkl. «Trin 1 (e)» firma.dk) er grøn i 1440 + 390.",
  "ja. Revert af 7eea845 (app/) på main gør den test rød.",
  "G-trin1-journey, G-kanaler-betaling, G-krav-chat-betaling-manuel (1440 + 390). Fejlklassen er søgt: ingen andre felter afviser et domæne uden skema "
  "(kun busy_ics_url kræver https/webcal, og det er bevidst).", "closed")
v("F-FIX20-01", "closed",
  "`tests/test_live_gate.py` 4/4 grøn. G-kanaler-betaling.spec og G-krav-chat-betaling-manuel.spec er grønne i 1440 + 390. Ét deltest er "
  "sprunget over med vilje, når Stripe er sat op (`acc.configured`).",
  "ja. Mutation: `subscription_required` er fjernet fra `webchat.unavailable_reasons`, og gaten er fjernet i `telephony.platform.activate`. Det gør alle 4 i "
  "test_live_gate.py røde.",
  "G01/G05-specs, launch-billing (C09), W04/W09/W11/W12/W13/BK02 (1440 + 390). Fejlklassen: telefonen bliver ved med at svare efter respitten "
  "(chat og kampagner stopper) → ny F-VER1113B-03-G01 (S1).", "closed",
  "Selve rettelsen (gaten ved go-live) virker. Hullet efter respitten er et nyt fund og ikke en genåbning, fordi F-FIX20-01 handlede om go-live.")
v("F-FIX26-01", "closed",
  "`tests/qa/test_qa_launch_billing.py::test_c09_*` og `tests/test_campaigns.py::test_start_is_explicit_and_honest` er grønne. launch-billing.spec er grøn i 1440 + 390. "
  "Én deltest er sprunget over efter datoen («the month just turned» er kun aktiv ved månedsskifte).",
  "ja. Hvis gaten i `_billing_ready` og `dispatch` fjernes, bliver begge tests røde. Hvis kun dispatch-gaten fjernes, bliver test_c09 stadig rød, så begge gates er dækket.",
  "C09/C15/B03-B05/M04 via launch-billing.spec; tests/test_billing_grace.py", "closed")
v("F-PBQ-06", "closed",
  "Privat-fake prod-build (NEXT_PUBLIC_PRIVAT_FAKE=1, :3438): `privat.spec.ts:554` (F-PBQ-06) 4/4 (375 + 1440 × begge projekter). Hele privat.spec 116/116. "
  "`tests/test_privat_plan_apps_lapse.py` og `test_qa_pd_billing::test_pc_ent_0[23]_*` er grønne.",
  "ja. Når apps.tsx fra 8ed36d9 vendes (fake/api.ts beholdt), fejler 1440-varianterne på «Kræver plan» (element(s) not found). 375-varianterne "
  "fejlede i `next dev`, fordi Next.js' dev-overlay opfangede klik. I prod-buildet er de grønne med rettelsen. Det var en harness-fejl og ingen produktfejl.",
  "privat.spec.ts (116, begge viewports)", "closed",
  "Fixerens ledger nævner kun 1440. Her er 375 også kørt.")
v("F-VF-01", "closed",
  "`ruff check app tests scripts client voice_pipeline tts_service browser_worker` er grøn på kandidaten. De 8 xfail(strict)-markører med fund-id står i "
  "test_qa_pd_{billing,sec,core}.py. Fuld pytest: se ledger.",
  "ja. `ruff` på test_qa_pd_billing/sec/core.py fra d0244464^ fejler (2/5/1 fejl). Fra d0244464 er de grønne.",
  "tests/qa/test_qa_pd_*.py (pd_sec alene: 66 passed, 5 xfailed)", "closed",
  "VF-01 blev rettet af en tidligere verifier (kun testfiler). Jeg er en anden agent end den.")
v("F-VER1113-01", "closed",
  "`test_w13_cancel_deletes_the_calendar_event_once[customer|staff]` og `test_calendar_delete_of_an_event_already_gone_is_success[410]` er grønne. "
  "W13.spec er grøn i 1440 + 390.",
  "ja. Revert af #229 (998d3587^1..998d3587, app/) gør de 3 tests røde (og test_w13_link_follows_a_moved_booking).",
  "W04/W09/W11/W12/W13/BK02 (1440 + 390). Fejlklassen: alle 5 kaldere af `bookings.cancel` kalder `mirror_cancel` præcis én gang "
  "(customer, bookings, sales channel, connector, admin/operations).", "closed")
v("F-VER1113-02", "closed", "`test_w13_link_follows_a_moved_booking` er grøn. W13.spec er grøn i 1440 + 390.",
  "ja. Den bliver rød ved revert af #229.",
  "W13, BK02. Fejlklassen: `bookings.service.move` er den eneste vej, der ændrer `ends_at`.", "closed")
v("F-VER1113-04", "closed",
  "`test_booking_door_needs_the_sms_code_for_a_phone_number` er grøn. W11/W12/W13/BK02/W04-specs er grønne i 1440 + 390 (frame.js' kodetrin til booking).",
  "ja. Revert af #233 (39a886fe^1..39a886fe, app/) gør testen rød, og også test_w12_widget_booking_states og test_bookings::test_webchat_booking_and_feed.",
  "W04, W04-sprog, W09, W11, W12, W13, BK02 (1440 + 390). Fejlklassen: webchat-assistentens `book_tid` gemmer et ubekræftet nummer → ny "
  "F-VER1113B-02-W04 (S3).", "closed",
  "Beslutningen (kode for telefonnummer på bookingdøren) er qa-leads sikrere standard. Fürster kan vende den.")
v("F-VER1113-06", "closed",
  "`test_ps_log_01_bearer_link_secrets_are_not_written_to_the_request_log` (4 nye parametre) er grøn. "
  "Reporterens scenarie `redact_path('/api/v1/public/customer/callback/T')` → `.../callback/***` (" + E + "redact-path-39a886f.txt).",
  "ja. Revert af #228 (app/) gør 4/4 nye parametre røde.",
  "W09, W13 (1440 + 390). Fejlklassen: E07's afmeldingslink `/public/booking-messages/unsubscribe/<token>` logges stadig i klartekst → "
  "ny F-VER1113B-01-W13 (S3).", "closed")
v("F-EA-04", "closed",
  "S02.spec «Kan ændre betyder det samme ved invitation og ved rolleskift» er grøn i 1440 + 390 (3/3 S02-tests pr. viewport).",
  "ja. Revert af #231 (team.tsx) + eget web-build (:3439 mod kandidatens API): S02.spec:25 rød i 1440 og 390 (Expected \"staff\", Received \"admin\"); de 2 andre S02-tests grønne.",
  "S02 (3), A05 (1) og M02 (2), 1440 + 390: 12/12", "closed",
  "Restfejl fra «Faktisk»: invitationssiden viser stadig «Medarbejder»/«Administrator»/«Læser» → ny F-VER1113B-04-S02 (S3).")
v("F-LEAD1113-01", "closed",
  "`scripts/check_live_schema.code_head()` → d6f2a8c4e1b7 (= `alembic heads`). `tests/test_schema_head.py` er grøn. Den planlagte Deploy check har ikke kørt "
  "siden #230 (sidste kørsel 16:24 var rød før rettelsen). Den skal bekræftes ved næste kørsel.",
  "ja. Revert af #230 (scripts/) gør `test_deploy_check_script_finds_the_same_single_head_as_alembic` rød med de 5 «heads» fra fundet.",
  "Regex'en dækker også en tuple over flere linjer (`[^)]*`). Alle down_revision-former i alembic/versions er tjekket (streng, tuple, None).", "closed")
v("F-LEAD1113-02", "closed",
  "`tests/qa/test_qa_M02.py` er grøn (inkl. `test_entitlements_and_readiness_in_detail` og den nye readiness-test). M02.spec er grøn i 1440 + 390.",
  "ja. Revert af #232 (app/) gør de 2 M02-tests røde.",
  "M02, S02, A05 (1440 + 390). readiness.py er læst: kun læsning (ingen get_or_create/sync/commit). Reglerne er de samme som i backend-gaterne "
  "(grace.subscription_paid, webchat.unavailable_reasons, campaigns).", "closed")
