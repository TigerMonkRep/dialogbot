---
id: F-PS-03-PC-INV-05
scenario: PC-INV-05
reported_by: security-privacy
severity: S1
status: closed
owner_fix: fix-engineer
related: [F-PS-02-PC-INV-05]
---

## Kort
Det globale loft på misses (1000/time på tværs af alle IP'er) lukker ALLE invitationer og gruppelinks for alle brugere – en anonym angriber kan med ~17 kald/minut holde invitationsflowet nede for hele Privat.

## Trin til at genskabe
1. Uden login: send `GLOBAL_MISSES_PER_HOUR` opslag på ukendte koder (`GET /privat/invites/by-code/<tilfældig>`), gerne fordelt på forfalskede IP'er (F-PS-02).
2. En rigtig gæst åbner et gyldigt link fra en ny IP: `GET /privat/invites/by-code/<gyldig>` → 429.
3. En indlogget bruger accepterer: `POST /privat/invites/{token}/accept` → 429.

## Forventet
Loftet skal stoppe opregning, ikke rigtige gæster med en gyldig kode. (lookup_limits.py: «Over a limit → 429 … also for codes that exist, so the answer reveals nothing» – fornuftigt pr. IP, men globalt rammer det alle.)

## Faktisk
Begge svar 429 `rate_limited` «Der er prøvet for mange links fra din forbindelse». Testen bruger loft 30 i stedet for 1000 (samme kode).

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_inv_05b_global_miss_ceiling_lets_anyone_lock_out_every_invitation

## Rodårsag (forslag)
app/modules/privat/lookup_limits.py `check()`: det globale miss-loft kastes før opslaget, uanset om koden findes. Forslag: gør det globale loft til en «hårdere» tilstand der kun rammer IP'er/klienter med misses (fx sænk per-IP miss-grænsen til 2/min mens loftet er nået) og lad hits gå igennem; accept for indloggede bør begrænses pr. bruger, ikke globalt. Alarmér operatør når loftet nås. Kræver F-PS-02 for at være robust.

## Rettelse (udfyldes af fix-engineer)
- Rettelse: det globale miss-loft afviser nu kun klienter, der selv har haft et miss inden for den sidste time. Hits og accept fra rene adresser går igennem. Når loftet nås, logges privat.lookup_global_ceiling. Robustheden afhænger af F-PS-02.
- Filer: app/modules/privat/lookup_limits.py; tests/test_privat_sharing.py::test_public_lookups_are_rate_limited er tilpasset den nye regel.
- Test: tests/qa/test_qa_pd_sec.py::test_ps_inv_05b
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (verifier, endelig Privat-runde 2026-11-11, HEAD 15c3704)
- Gentest: HEAD 15c3704: grøn i fuld pytest (2 shards, egne db'er qa_privfinal_t/_t2) – test_ps_inv_05b, test_public_lookups_are_rate_limited
- Fejler testen uden rettelsen? ja – fejler på f2b3d11 (før Privat-rettelserne; HEAD's tests/ lagt oven på, fixture uden signup_intent)
- Naboscenarier kørt: test_qa_pd_sec.py, test_privat_sharing.py
- Dom: closed
