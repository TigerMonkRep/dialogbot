import { appSuite, household } from "./suite";

/** PC-APP-HUS-OG-VEDLIGEHOLD-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "hus-og-vedligehold", sc: "PC-APP-HUS-OG-VEDLIGEHOLD", plan: true,
  say: "Tilføj alle de faste opgaver i huset",
  shows: /Test røgalarmerne/,
  ...household("hus-og-vedligehold"),
});
