import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";

/* QA M02 (e2e-erhverv A): /admin/workspaces[/:id] (→ /app/operator/admin/kunder[/id]) – business search, detail,
 * entitlements, readiness, scoped support context. Source: operator/admin/{kunder,shared}.tsx, app/modules/admin. */
const EVID = "../qa/evidence/M02";
const CSRF = { "x-requested-with": "dialogbot" };

test("M02 · kunde nægtes; operatør søger, åbner kunden og ser medlemmer uden hemmeligheder", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  await page.goto("/app/operator/admin/kunder");
  await expect(page.getByText("Admin er kun for Dialogbot-operatører.")).toBeVisible();
  await page.context().clearCookies();

  const op = await freshOwner(page, info);
  const name = ((await (await page.request.get(`/api/backend/workspaces/${op.wsId}`)).json()) as { name: string }).name;
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin/kunder");
  await page.getByRole("searchbox", { name: "Søg" }).or(page.getByLabel("Søg")).first().fill(name);
  await page.getByRole("button", { name: "Søg" }).click();
  await expect(page).toHaveURL(/\?q=/);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Medlemmer/ })).toBeVisible();
  // Entitlements and goal-specific readiness (13/11): a fresh customer has not paid and nothing may go live.
  const ent = page.getByRole("region", { name: "Rettigheder" });
  await expect(ent.getByText("ikke betalt")).toBeVisible();
  await expect(ent.getByText("Telefon/chat må gå live")).toBeVisible();
  const ready = page.getByRole("region", { name: /^Opsætning/ });
  await expect(ready.getByText("Virksomhed", { exact: true })).toBeVisible();
  await expect(ready.getByText("Betaling", { exact: true })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toMatch(/argon2|token_hash|password_hash/);
  await page.screenshot({ path: `${EVID}/${info.project.name}-kunde.png`, fullPage: true });
  // empty search
  await page.goto("/app/operator/admin/kunder?q=qa-findes-ikke-zzz");
  await expect(page.getByText("Ingen kunder matcher.")).toBeVisible();
});

test("M02 · en ukendt kunde vises som «findes ikke» – ikke som «kun for operatører»", async ({ page }, info) => {
  await freshOwner(page, info);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin/kunder/00000000-0000-4000-8000-000000000000");
  await page.screenshot({ path: `${EVID}/${info.project.name}-ukendt-kunde.png`, fullPage: true });
  await expect(page.getByText("Admin er kun for Dialogbot-operatører."), "an operator is told he is not an operator").toHaveCount(0);
});
