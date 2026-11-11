---
id: F-PS-04-PC-INV-04
scenario: PC-INV-04
reported_by: security-privacy
severity: S0
status: closed
owner_fix: fix-engineer
related: []
---

## Kort
Invitationstokens, korte invitationskoder og gruppelink-koder (bearer-hemmeligheder) skrives i klartekst i request-loggen.

## Trin til at genskabe
1. Åbn en delt liste/ønskeliste via `/privat/invitation/<token>` eller `/i/<kode>`.
2. Se API-loggen (`/home/claude/pd-api.log` i QA; i drift Render-loggen).

## Forventet
Hemmeligheder må ikke stå i logs (sikkerhedskrav «Secrets: none in … logs»). app/core/logging.py redigerer allerede kalender-feedets token af samme grund.

## Faktisk
`"path": "/api/v1/privat/invites/WyXshO-…-EZM"` og `…/invites/<token>/accept` står i QA-loggen (tokens maskeret her). Ingen af `/privat/invites/{token}`, `/invites/{token}/accept`, `/invites/by-code/{code}[/accept]`, `/group-invites/by-code/{code}[/join]` redigeres. Den, der kan læse loggen (Render-adgang, log-drain/tredjepart), kan melde sig ind på private lister og ønskelister (og som giver se reservationer) i 30 dage, eller melde sig ind i en gruppe.
Alvorsgrad S0 efter reglen «enhver hemmelighed i logs»; den praktiske eksponering er begrænset til log-læsere.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_log_01_bearer_link_secrets_are_not_written_to_the_request_log (6 af 7 stier fejler; feed består)
- Log: /home/claude/pd-api.log (grep `privat/invites/`)

## Rodårsag (forslag)
app/core/logging.py:39 `_SECRET_PATHS = re.compile(r"(/privat/calendar/feed/)[^/]+")` – udvid til `(/privat/(?:calendar/feed|invites(?:/by-code)?|group-invites/by-code)/)[^/]+`. Overvej også Erhvervs `/invitations/…`-stier, hvis token står i stien.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: logging.redact_path redigerer nu /privat/calendar/feed/, /privat/invites/{token}, /privat/invites/by-code/{code}, /privat/group-invites/by-code/{code}, /invitations/{token} og /public/offers/{token}. db.error-loggen bruger også redact_path.
- Filer: app/core/logging.py, app/core/errors.py
- Test: tests/qa/test_qa_pd_sec.py::test_ps_log_01_* (grønne)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_ps_log_01 (7 stier)
- Fejler testen uden rettelsen? ja – 6 af 7 stier fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent) (kalender-feed var allerede ok)
- Naboscenarier kørt: test_qa_pd_sec.py
- Dom: closed
