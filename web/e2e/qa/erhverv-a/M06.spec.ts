import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* QA M06 (e2e-erhverv A): /admin/support – support queue, ticket detail, assignment, client-visible replies.
 * The operator admin lives at /app/operator/admin (web/src/app/app/(admin)/operator/admin/shared.tsx TABS). */
const EVID = "../qa/evidence/M06";
const CSRF = { "x-requested-with": "dialogbot" };

test("M06 · operatørens supportkø findes", async ({ page }, info) => {
  test.fail(true, "M06/H01 operator support queue: not-implemented");
  await freshOwner(page, info);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin");
  const tabs = await page.getByRole("navigation", { name: "Admin" }).getByRole("link").allInnerTexts();
  info.annotations.push({ type: "admin-tabs", description: tabs.join(", ") });
  await page.screenshot({ path: `${EVID}/${info.project.name}-admin-faner.png`, fullPage: true });
  const statuses: Record<string, number | undefined> = {};
  for (const p of ["/admin/support", "/app/operator/support", "/app/operator/admin/support"]) statuses[p] = (await page.request.get(p)).status();
  info.annotations.push({ type: "routes", description: JSON.stringify(statuses) });
  expect(tabs.some((t) => /support/i.test(t)) || Object.values(statuses).some((s) => s === 200), `no support queue: tabs=${tabs.join("|")} routes=${JSON.stringify(statuses)}`).toBeTruthy();
});
