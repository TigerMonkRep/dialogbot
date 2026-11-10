---
id: F-PS-02-PC-INV-05
scenario: PC-INV-05
reported_by: security-privacy
severity: S1
status: needs-decision
owner_fix: fix-engineer
related: [F-PS-01-PC-GRP-04, F-PS-03-PC-INV-05]
---

## Kort
Alle per-IP-grænser på offentlige Privat-opslag (invitationer, gruppelinks, gruppe-join/SMS) og funnel kan omgås: backend tager første `X-Forwarded-For`-værdi, som klienten selv skriver.

## Trin til at genskabe
1. Uden login: 60× `GET /api/v1/privat/invites/by-code/QQQQ00nn` på under ét minut med `X-Forwarded-For: 203.0.113.<n>, 10.0.0.1` (skiftende første værdi).
2. Alle 60 svarer 404 – aldrig 429.

## Forventet
lookup_limits.py: «misses … 10/minute and 50/day» pr. IP. Grænsen skal gælde den reelle klient, ikke en header klienten styrer.

## Faktisk
60/60 misses → 404, ingen 429. `client_ip()` (app/modules/privat/lookup_limits.py:42-44) returnerer `X-Forwarded-For.split(",")[0]`. API'et er offentligt (infra/render.yaml: `type: web`, domæne `api.dialogbot.dk`), og Renders proxy tilføjer (append) klientens IP sidst – den første værdi er klientens egen. Samme `client_ip` bruges i app/modules/funnel/limits.py:18.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_inv_05a_forwarded_for_rotation_bypasses_the_per_ip_lookup_limits
- Verificér på Render (kun læsning af egen request mod QA – ikke prod): header-rækkefølgen er antaget ud fra append-adfærd.

## Rodårsag (forslag)
Tag den IP, den betroede proxy har sat: den SIDSTE værdi i X-Forwarded-For (Render) – eller når kaldet kommer via web-BFF'en (Vercel), en værdi BFF'en signerer/sætter i en header, som API'et kun stoler på med en delt hemmelighed (fx `X-Dialogbot-Client-IP` + HMAC). Alternativt `uvicorn --proxy-headers --forwarded-allow-ips=<Render>` og brug `request.client.host`.

## Rettelse (udfyldes af fix-engineer)
- Ikke rettet – kræver drift/konfiguration. Første X-Forwarded-For-værdi er klientstyret. Den sidste værdi er den IP, Render ser, og for al trafik via web-BFF'en er det Vercels egress-IP, så alle web-brugere ville dele én kvote. Den korrekte løsning: BFF'en (web/src/app/api/backend/[...path]/route.ts) sender klientens IP i en header sammen med en delt hemmelighed (ny env-variabel på både Vercel og Render), og API'et (lookup_limits.client_ip, funnel/limits) stoler kun på headeren ved match – ellers bruges den sidste XFF-værdi.
- Mulige veje: (a) som ovenfor – kræver at Fürster/drift opretter og sætter hemmeligheden i begge miljøer; (b) uvicorn --proxy-headers med Renders proxy-IP'er + BFF-hemmelighed; (c) acceptér risikoen (koder er 8 tegn fra 31 – brute force er upraktisk; F-PS-03 begrænser nu lock-out).
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
