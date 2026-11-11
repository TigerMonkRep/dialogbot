import { appSuite, household } from "./suite";

/** PC-APP-FAELLES-UDGIFTER-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "faelles-udgifter", sc: "PC-APP-FAELLES-UDGIFTER", plan: false,
  say: "Jeg betalte 1.200 kr. for mad i sommerhuset – vi er Anna, Bo og mig",
  shows: /Anna betaler 400 kr\. til Mette/,
  tasksTitle: "Udgifter: sommerhuset",
  ...household("faelles-udgifter"),
});
