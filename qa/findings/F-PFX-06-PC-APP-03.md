---
id: F-PFX-06-PC-APP-03
scenario: PC-APP-03
reported_by: fix-engineer #2 (katalog qa/privat/scenarios.csv)
severity: S1
status: fixed
owner_fix: fix-engineer
related: []
---

## Kort
Fitness lover «Gemmer aldrig vægt, sygdom … medicin», men det blev kun håndhævet i modellens prompt. Serveren gemte målet ordret, fx «jeg vejer 92 kg og tager blodtryksmedicin» (GDPR art. 9).

## Rettelse (udfyldes af fix-engineer)
- Rettelse: fitness.without_health fjerner på serveren hver sætning – eller del mellem komma/«og»/«men» – der nævner krop eller helbred (vægt/kg, medicin, blodtryk, sygdom, skade, gravid, tabe mig …), før mål og aktivitet gemmes (set_goal, plan, log). Løftet i appteksten holder nu.
- Begrænsning: ordlisten fanger de almindelige danske ord, ikke alle omskrivninger. Prompt-reglen er stadig første forsvar.
- Filer: app/modules/privat/fitness.py
- Test: tests/qa/test_qa_pd_apps_a.py::test_pa_fitness_server_has_no_guard_for_health_words (grøn)
- Commit: (qa-lead committer; arbejdskopi /home/claude/wt-privat)

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
