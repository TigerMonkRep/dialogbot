---
id: F-PS-10-PC-ACC-05
scenario: PC-ACC-05
reported_by: security-privacy
severity: S2
status: new
owner_fix: fix-engineer
related: [F-PS-05-PC-ACC-02]
---

## Kort
Rejser gemmer brugerens søgninger (hvorfra, hvortil, hvornår) i private_app_data, men appen er markeret «ingen data at slette», så brugeren kan aldrig slette dem.

## Trin til at genskabe
1. Rejser med søgning (travel.py:359-361 `appdata.put(..., {"searches": …})`).
2. `app_status.deletable("rejser")` → False (app_status.py:87 lister "rejser" sammen med apps, der ikke har egne data); Butik/Mine apps viser ikke «Slet appens data».

## Forventet
Scenariet: «søgninger kan ikke slettes af brugeren → rapportér S2». Rejseplaner er persondata; de skal kunne slettes som de andre apps' data.

## Faktisk
Søgningerne bliver liggende; `DELETE /privat/addons/rejser/data` tilbydes ikke.

## Evidens
- Test: tests/qa/test_qa_pd_sec.py::test_ps_acc_05_trip_searches_are_kept_but_marked_not_deletable (rød)

## Rodårsag (forslag)
app/modules/privat/app_status.py:87: fjern "rejser" fra listen, så `_data_tables` falder til PrivateAppData for app_key "rejser" (eller begræns gemte søgninger til fx 10 og 90 dage).

## Rettelse (udfyldes af fix-engineer)
- Filer:
- Commit:

## Verifikation (udfyldes af verifier)
- Gentest:
- Dom: closed | reopened
