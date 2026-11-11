import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { EVID } from "./d-helpers";

/* Webhook URLs point at https://localhost (resolvable in the sandbox, ALLOW_PRIVATE_FETCH=true; fake connectors never deliver).
 * S04 – /app/settings/integrations/:id: «Configure supported API/database or delivery connection, scope, test and sync;
 * calendar entries open canonical BK07 instead of a duplicate editor.» Built inline on the connector card. */
const card = (page: import("@playwright/test").Page, key: string) => page.locator(`li[data-connector="${key}"]`);

test("S04 · webhook (leveringsforbindelse): URL valideres, forbind viser signeringsnøgle én gang, test virker, URL rettes og gemmes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=integrationer");
  const c = card(page, "webhook");
  const connect = c.getByRole("button", { name: "Forbind" });
  await expect(connect).toBeDisabled(); // no URL yet
  await c.getByRole("textbox").fill("https://localhost/fjordgulv-hook");
  await connect.click();
  await expect(c.locator("code")).toBeVisible(); // signing secret shown once
  await c.getByRole("button", { name: "Test forbindelse" }).click();
  await expect(c.getByText(/Forbindelsen virker/)).toBeVisible();
  await c.getByRole("textbox").fill("https://localhost/fjordgulv-hook-v2");
  await c.getByRole("button", { name: /Gem/ }).click();
  await expect.poll(async () => ((await (await page.request.get(`/api/backend/workspaces/${wsId}/integrations`)).json()).items.find((x: { key: string }) => x.key === "webhook")?.config?.url)).toBe("https://localhost/fjordgulv-hook-v2");
  await page.reload();
  await expect(card(page, "webhook")).toContainText("Forbundet");
  await expect(card(page, "webhook").locator("code")).toHaveCount(0); // the secret is not shown again
  await page.screenshot({ path: `${EVID("S04")}/${info.project.name}-webhook.png`, fullPage: true });
});

test("S04 · webhook-URL der ikke er https afvises med en forståelig fejl", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=integrationer");
  const c = card(page, "webhook");
  await c.getByRole("textbox").fill("ftp://hooks.example.com/x");
  await c.getByRole("button", { name: "Forbind" }).click();
  await expect(c.getByRole("alert").or(c.locator("[role=status]")).first()).toBeVisible();
  await expect(c).toContainText("Ikke forbundet");
});

test("S04 · kravets detaljeadresse /app/settings/integrations/:id findes (fx google_calendar → BK07/aftaler)", async ({ page }, info) => {
  test.fail(true, "F-E2D-15-S04: S3 new – Kravets adresser /app/settings/integrations og /app/settings/integrations/:id giver 404 – kun …");
  await freshOwner(page, info);
  const r = await page.request.get("/app/settings/integrations/google_calendar", { maxRedirects: 5 });
  test.info().annotations.push({ type: "status", description: `${r.status()} ${r.url()}` });
  expect(r.status()).toBe(200);
});
