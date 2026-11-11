import { expect, test } from "@playwright/test";
import { login, SEEDED } from "../../helpers";

/* M05 – /admin/templates: «Editable business taxonomy, question/script templates, versions and publishing status.»
 * (DB-009). Not built: no route under /admin or /app/operator/admin. A customer must never reach it either. */
test("M05 · platformsskabeloner findes for operatører – og kunden kan ikke nå dem", async ({ page }) => {
  test.fail(true, "M05: not-implemented – platformsskabeloner /admin/templates (DB-009)");
  await login(page, SEEDED.owner);
  for (const p of ["/admin/templates", "/app/operator/admin/templates", "/app/operator/admin/skabeloner"]) {
    const r = await page.request.get(p, { maxRedirects: 5 });
    test.info().annotations.push({ type: "status", description: `${p} → ${r.status()}` });
  }
  // a customer owner gets no operator tools
  await page.goto("/app/operator/admin");
  await expect(page.getByText(/kun for Dialogbot-operatører/)).toBeVisible();
  const r = await page.request.get("/admin/templates", { maxRedirects: 5 });
  expect(r.status(), "route for operators").toBe(200);
});
