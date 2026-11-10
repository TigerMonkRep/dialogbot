---
id: F-PS-02-PC-INV-05
scenario: PC-INV-05
reported_by: security-privacy
severity: S1
status: new
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
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
