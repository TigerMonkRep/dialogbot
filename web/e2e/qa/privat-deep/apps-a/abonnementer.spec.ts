import { appSuite, household } from "./suite";

/** PC-APP-ABONNEMENTER-01..05 in the browser against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "abonnementer", sc: "PC-APP-ABONNEMENTER", plan: true,
  say: "Jeg har Netflix til 139 kr. om måneden og Telia til 199 kr. med binding til 2027-03-01",
  shows: /2 abonnementer – 338 kr\. om måneden/,
  ...household("abonnementer"),
});
