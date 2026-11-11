import { appSuite, household } from "./suite";

/** PC-APP-GARANTI-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "garanti", sc: "PC-APP-GARANTI", plan: true,
  say: "Jeg købte en vaskemaskine i Elgiganten den 2026-05-03 til 4.999 kr.",
  shows: /reklamationsret til 3\. maj 2028/,
  ...household("garanti"),
});
