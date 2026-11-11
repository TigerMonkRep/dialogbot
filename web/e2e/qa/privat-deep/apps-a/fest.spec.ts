import { appSuite, household } from "./suite";

/** PC-APP-FEST-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "fest", sc: "PC-APP-FEST", plan: false,
  say: "Lav en fest: Idas 10-års fødselsdag den 2027-03-06 kl. 14 med Emma, Noah og Alma",
  shows: /Idas 10-års fødselsdag/,
  ...household("fest"),
});
