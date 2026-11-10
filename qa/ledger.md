# QA-ledger

Én linje pr. hændelse. Nyeste nederst.

| Tid | Fra → Til | Type | Emne | Kort |
|---|---|---|---|---|
| 11:40 | e2e-erhverv-B → qa-lead | finding | C09 C11 C15 M04 W04 W09 W12 W13 BK06 BK15 | 7 fund (1×S0, 2×S1, 3×S2, 1×S3); C09/M04/W04/W09/W13 not-implemented |
| 11:42 | qa-lead → fix-engineer | handoff | F-EB-01..07 | S0 genopkald-loop bekræftet i campaigns/service.py:322-330; batch 1 sendt |
| 11:42 | qa-lead → voice-qa | handoff | F-EB-05, F-EB-01 | Peter bekræfter booking selv ved kalenderfejl – tilføj eval-case |
| 11:42 | qa-lead → (Fürster) | needs-decision | C09 C15 M04 | Kampagner afregnes pr. opkald, ikke forudbetalte pakker – udgår kravene? |
| 12:07 | billing-qa → qa-lead | finding | B03 B04 B05 B06 X08 X28 | 10 fund F-BQ-001..010 (6×S1, 2×S2, 2×S3; 2 needs-decision); B03/B04/B05 not-implemented; tabel qa/billing/expected-vs-actual.md |
| 12:10 | integrations-qa → qa-lead | finding | E07 X26 | 8 fund F-IQ-01..08 (1×S1, 5×S2, 2×S3); E07 not-implemented; matrix qa/integrations/status.md |
| 12:20 | billing-qa → qa-lead | finding | B03-B06 X08 X28 | 10 fund (6×S1); B03/B04/B05 not-implemented; DB-001/002/003 regressionstests grønne |
| 12:22 | qa-lead → fix-engineer | handoff | F-BQ-002..010 | batch 2 (billing); F-BQ-001/005 needs-decision |
| 12:30 | integrations-qa → qa-lead | finding | E07 X26 | 8 fund (1×S1); E07 not-implemented; Fürster: tjek VAPI_SERVER_SECRET på worker |
| 12:33 | i18n-a11y-qa → qa-lead | finding | X24 | 8 sprog holder på 6 sider; 5 fund (funnel-fejl på dansk, kontrast, aria) |
| 12:35 | e2e-erhverv-A → qa-lead | finding | A01 A05 A06 S02 H01 M02 M03 M06 X01 | 10 fund (3×S1); X01/A05 pass; H01/M03/M06 not-implemented |
| 12:36 | qa-lead → fix-engineer | handoff | F-EA/F-IQ/F-LQ | batch 3; F-EA-04 needs-decision |
| 2026-11-10 | voice-qa → qa-lead | finding | X05 X15 X16 R02 R03 | F-VQ-01..09 + BK15-eval (F-EB-05 bekræftet i Peter-stien) |
| 12:20 | security-privacy → qa-lead | finding | X29 X20 | X29 IDOR-sweep 487/487 grøn (ingen krydslæsning/-skrivning); F-SQ-01 (dev-mailbox wildcard → operatør-overtagelse, S1), F-SQ-02 (DB-parametre inkl. argon2-hash i logs, S1), F-SQ-03 (M07 ikke bygget, S2) |
| 12:45 | voice-qa → qa-lead | finding | R02 R03 X05 X15 X16 | 9 fund (3×S1); X16 kræver live-test med Fürsters ja; ingen «privat preview» i prompts |
| 12:46 | qa-lead → fix-engineer | handoff | F-VQ-01..09 | batch 4 + create_call skal respektere TELEPHONY_PROVIDER=fake; F-VQ-05 needs-decision |
