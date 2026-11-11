---
id: F-VF-02-PC-I18N
scenario: PC-I18N / X24
reported_by: verifier
severity: S3
status: new
owner_fix: fix-engineer
related: [F-JP-07-X10, F-PX-05-PC-I18N-02]
---

## Kort
Samme fejlklasse som F-JP-07: opgavebeskeder (mail + push) har hårdkodet danske emner, også for en bruger med interface_language=en/de. Mailens ramme er oversat, men emnet/titlen er dansk.

## Trin
`service.notify_owner(...)` kaldes med `subject=f"Opkald til {c.business_name}"` (calls.py:512, 636, 867), `f"{…} ringede tilbage"` (805), `f"{…} har åbent nu"` (882), `f"Godkend booking hos {biz}"`, `f"Booket hos …"`, `f"Tjek din booking hos …"` (browser/service.py:255–344). Påmindelsens push-titel «Påmindelse» (service.py:398).

## Forventet
Emne og push-titel på brugerens sprog (8 sprog), som privat_mails' faste tekster.
