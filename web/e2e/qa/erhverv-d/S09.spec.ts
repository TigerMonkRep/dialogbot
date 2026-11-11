import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";
import { CSRF, EVID } from "./d-helpers";

/* S09 – /app/settings/activity: «Readable workspace activity/audit trail with actor, time and changed object.»
 * Redirects to /app/indstillinger?ark=log. */
test("S09 · loggen viser hvem og hvornår, nyeste først, og tælleren passer med API'et", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.request.post(`/api/backend/workspaces/${wsId}/categories`, { headers: CSRF, data: { label: "Gulvafslibning", slug: null, is_primary: true } });
  await page.goto("/app/settings/activity");
  await expect(page).toHaveURL(/ark=log/);
  const api = await (await page.request.get(`/api/backend/workspaces/${wsId}/audit?limit=25`)).json();
  await expect(page.getByText(new RegExp(`^${api.total} `))).toBeVisible();
  const rows = page.locator("ol > li");
  await expect(rows).toHaveCount(Math.min(api.total, 25));
  await expect(rows.first()).toContainText("E2E Ejer"); // actor
  await expect(rows.first()).toContainText(/\d{1,2}[.:]\d{2}/); // time
  await page.screenshot({ path: `${EVID("S09")}/${info.project.name}-log.png`, fullPage: true });
});

test("S09 · det ændrede objekt står i loggen (fx hvilken kategori, hvilken side af profilen)", async ({ page }, info) => {
  test.fail(true, "F-E2D-17-S09: S2 new – Aktivitetsloggen viser hvem og hvornår, men ikke hvad der blev ændret: «Kategori tilføjet · E2E …");
  const { wsId } = await freshOwner(page, info);
  await page.request.post(`/api/backend/workspaces/${wsId}/categories`, { headers: CSRF, data: { label: "Gulvafslibning", slug: null, is_primary: true } });
  const api = await (await page.request.get(`/api/backend/workspaces/${wsId}/audit?limit=5`)).json();
  expect(api.items[0].action).toBe("category.added");
  await page.goto("/app/indstillinger?ark=log");
  const first = page.locator("ol > li").first();
  await page.screenshot({ path: `${EVID("S09")}/${info.project.name}-objekt.png`, fullPage: true });
  // the audit row has object_type/after (the category); the page renders only the action label, actor and time
  await expect(first).toContainText("Gulvafslibning");
});

test("S09 · læser ser ikke loggen, og API'et afviser", async ({ page }) => {
  await login(page, SEEDED.reader);
  await page.goto("/app/indstillinger?ark=log");
  await expect(page.locator("ol > li")).toHaveCount(0);
  const wss = await (await page.request.get("/api/backend/workspaces")).json();
  const wsId = ((wss.items ?? wss)[0]).id as string;
  expect((await page.request.get(`/api/backend/workspaces/${wsId}/audit?limit=5`)).status()).toBe(403);
});
