import { expect, test } from "@playwright/test";
import { login, SEEDED } from "../../helpers";

/* QA H01 (e2e-erhverv A): /app/help and /app/support/:ticket – contextual help, support request with attachments,
 * status and thread. Source: web/src/app/app/(admin)/hjaelp/page.tsx; next.config.ts MOVED (/app/help → /app/hjaelp). */
const EVID = "../qa/evidence/H01";

test("H01 · hjælpen findes, alle «Gå dertil»-links virker, og der lyves ikke om support", async ({ page }, info) => {
  await login(page, SEEDED.staff);
  await page.goto("/app/help");
  await expect(page).toHaveURL(/\/app\/hjaelp$/);
  await expect(page.getByRole("heading", { level: 1, name: "Sådan bruger I Dialogbot" })).toBeVisible();
  const hrefs = [...new Set(await page.getByRole("link", { name: "Gå dertil" }).evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).getAttribute("href")!)))];
  expect(hrefs.length).toBeGreaterThan(5);
  for (const h of hrefs) {
    const r = await page.request.get(h);
    expect(r.status(), `help link ${h}`).toBeLessThan(400);
  }
  expect(await page.locator("body").innerText()).not.toMatch(/staging/i);
  await page.screenshot({ path: `${EVID}/${info.project.name}-hjaelp.png`, fullPage: true });
});

test("H01 · supportsager (/app/support/:ticket) findes", async ({ page }, info) => {
  test.fail(true, "H01 support ticket page: not-implemented");
  await login(page, SEEDED.owner);
  const r = await page.goto("/app/support/1");
  await page.screenshot({ path: `${EVID}/${info.project.name}-support-ticket.png`, fullPage: true });
  info.annotations.push({ type: "status", description: `GET /app/support/1 → ${r?.status()}` });
  // Requirement: a support request with attachments, status and thread. Not implemented → this test documents it.
  expect(r?.status(), "support ticket page must exist").toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});
