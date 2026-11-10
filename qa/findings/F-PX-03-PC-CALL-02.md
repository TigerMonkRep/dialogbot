---
id: F-PX-03-PC-CALL-02
scenario: PC-CALL-02
reported_by: voice-qa (PX)
severity: S2
status: new
owner_fix: fix-engineer
related: []
---

## Kort
Navne-hjælpen til talegenkendelsen virker ikke i Privat-opkald: brugerens navn og virksomhedens navn sendes som `extra` til `vapi.transcriber_for(db, None, …)`, men funktionen springer keyterm/customVocabulary over, når `ws is None`.

## Trin til at genskabe
1. Plus-bruger «Bjørk Æblegård», godkend opkald til Cykelmageren.
2. Se `assistant.transcriber` i payloaden (/__qa/calls eller testens optager).

## Forventet
vapi.transcriber_for-docstring: «`extra` are terms this one call will hear: the person we ring and their company, which the generic model otherwise mishears». Navnestavning er en kernedisciplin for Peter (voice-qa §2).

## Faktisk
`{"provider":"deepgram","model":"nova-3","language":"da",…}` uden `keyterm` – hverken «Bjørk», «Æblegård» eller «Cykelmageren». Årsag: `for d in […]: if ws is None: continue` (app/modules/telephony/vapi.py ~l. 362) – også `own`-listen kasseres.

## Evidens
- Test: tests/qa/test_qa_pd_x.py::test_px_voice_script_language_names_and_peter (rød)

## Forslag
Tilføj `own` som keyterm/customVocabulary også når `ws is None` (kun forretningens egne keyterms kræver en workspace).

## Rodårsag (udfyldes af fix-engineer)
## Rettelse (udfyldes af fix-engineer)
## Verifikation (udfyldes af verifier)
