import { appSuite, household } from "./suite";

/* Håndværker: the QA stack has no Google key (DemoPlaces) – the search finds no callable painters, so the core flow
 * ends in «Jeg fandt ingen …». The data-holding half (03/04/05) is therefore marked fixme here; proposals-only and
 * «never dialled» are covered in tests/qa/test_qa_pd_apps_a.py and tests/test_privat_household.py. */
/** PC-APP-HAANDVAERKER-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "haandvaerker", sc: "PC-APP-HAANDVAERKER", plan: true,
  say: "Find 3 malere i Aarhus og hent tilbud på at male stuen",
  shows: /./,
  ...household("haandvaerker"),
  skip: { "03": "ingen ringbare malere i QA-stakken (DemoPlaces)", "04": "ingen tilbud at fjerne uden opkald", "05": "intet at gemme uden opkald" },
});
