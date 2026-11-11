import { appSuite, household } from "./suite";

/** PC-APP-FLYTNING-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "flytning", sc: "PC-APP-FLYTNING", plan: true,
  say: "Vi flytter til Odense den 2027-04-01",
  shows: /Flyttedag 1\. april 2027 til Odense/,
  tasksTitle: "Flytning: Odense",
  ...household("flytning"),
});
