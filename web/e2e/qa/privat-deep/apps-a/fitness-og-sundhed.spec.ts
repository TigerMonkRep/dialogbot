import { appSuite, household } from "./suite";

/** PC-APP-FITNESS-OG-SUNDHED-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "fitness-og-sundhed", sc: "PC-APP-FITNESS-OG-SUNDHED", plan: true,
  say: "Jeg vil løbe tirsdag og torsdag kl. 17 – målet er 5 km i maj",
  shows: /Tirsdag: Løb/,
  ...household("fitness-og-sundhed"),
});
