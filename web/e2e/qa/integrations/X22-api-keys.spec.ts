import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";

/* X22 / F-M2-06-X22 (verifier, bølge 2): kortet «API-nøgler» under Integrationer.
 * public-api.md §1: «API-nøgle fra Integrationer → API-nøgler i appen». Klikkes igennem som en kunde:
 * opret (navn + scope) → den fulde nøgle vises ÉN gang → efter reload kun maskeret (prefix…last4) → nøglen virker mod
 * /v1/me → tilbagekald (med bekræftelse) → nøglen afvises (401). Læser/medarbejder ser ikke kortet. */
const API = process.env.API_BASE_URL ?? "http://localhost:8200";
const EVID = `${__dirname}/../../../../qa/evidence/X22`;

test("X22 · API-nøgler: opret → vist én gang → maskeret efter reload → virker → tilbagekald → afvist", async ({ page }, info) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=integrationer");
  const card = page.locator("section[aria-labelledby='api-keys-h']");
  await expect(card.getByRole("heading", { name: "API-nøgler" })).toBeVisible();
  await expect(card).toContainText("Ingen nøgler endnu.");

  // Opret-knappen er slået fra uden navn og uden scope
  const create = card.getByRole("button", { name: "Opret nøgle" });
  await expect(create).toBeDisabled();
  const name = `CRM-sync ${info.project.name}`;
  await card.getByLabel("Navn").fill(name);
  await expect(create).toBeDisabled();
  await card.locator("label", { hasText: "leads:read" }).first().getByRole("checkbox").check();
  await expect(create).toBeEnabled();
  await create.click();

  // Den fulde nøgle vises én gang
  const shown = card.locator("[data-api-key]");
  await expect(shown).toBeVisible();
  const key = (await shown.textContent())!.trim();
  expect(key.length).toBeGreaterThan(20);
  await expect(card).toContainText(`Nøglen «${name}» – kopiér den nu`);
  await card.getByRole("button", { name: "Kopiér" }).click();
  await expect(card.getByRole("button", { name: "Kopieret" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(key);

  const row = card.locator("[data-api-key-row]", { hasText: name });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("leads:read");
  await expect(row).toContainText("aldrig brugt");
  await expect(row).not.toContainText(key);
  await page.screenshot({ path: `${EVID}/${info.project.name}-api-noegle-vist-en-gang.png`, fullPage: true });

  // Nøglen virker mod public API
  const me = await page.request.get(`${API}/v1/me`, { headers: { Authorization: `Bearer ${key}` } });
  expect(me.status()).toBe(200);

  // Reload: nøglen står aldrig i klartekst igen – kun prefix…last4
  await page.reload();
  await expect(card.locator("[data-api-key]")).toHaveCount(0);
  expect(await page.content()).not.toContain(key);
  const masked = card.locator("[data-api-key-row]", { hasText: name });
  await expect(masked).toContainText(`…${key.slice(-4)}`);
  await expect(masked).toContainText(/sidst brugt/);

  // Tilbagekald: annulleret bekræftelse ændrer intet
  page.once("dialog", (d) => d.dismiss());
  await masked.getByRole("button", { name: "Tilbagekald" }).click();
  await expect(masked.getByRole("button", { name: "Tilbagekald" })).toBeVisible();
  expect((await page.request.get(`${API}/v1/me`, { headers: { Authorization: `Bearer ${key}` } })).status()).toBe(200);

  page.once("dialog", (d) => { expect(d.message()).toContain(`Tilbagekald «${name}»?`); void d.accept(); });
  await masked.getByRole("button", { name: "Tilbagekald" }).click();
  await expect(masked).toContainText(/tilbagekaldt/);
  await expect(masked.getByRole("button", { name: "Tilbagekald" })).toHaveCount(0);
  expect((await page.request.get(`${API}/v1/me`, { headers: { Authorization: `Bearer ${key}` } })).status()).toBe(401);
  await page.reload();
  await expect(card.locator("[data-api-key-row]", { hasText: name })).toContainText(/tilbagekaldt/);
  await page.screenshot({ path: `${EVID}/${info.project.name}-api-noegle-tilbagekaldt.png`, fullPage: true });
});

test("X22 · API-nøgler: medarbejder ser ikke kortet (api_keys.manage = ejer/admin)", async ({ page }) => {
  await login(page, SEEDED.staff);
  await page.goto("/app/indstillinger?ark=integrationer");
  await page.waitForLoadState("networkidle");
  await expect(page.locator("section[aria-labelledby='api-keys-h']")).toHaveCount(0);
});

test("X22 · API-nøgler: 3. aktive nøgle afvises med forståelig dansk fejl, og ingen nøgle vises", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  for (const n of ["A", "B"]) {
    const r = await page.request.post(`/api/backend/workspaces/${wsId}/api-keys`, { headers: CSRF, data: { name: n, scopes: ["leads:read"] } });
    expect(r.status()).toBe(201);
  }
  await page.goto("/app/indstillinger?ark=integrationer");
  const card = page.locator("section[aria-labelledby='api-keys-h']");
  await expect(card.locator("[data-api-key-row]")).toHaveCount(2);
  await card.getByLabel("Navn").fill("C");
  await card.locator("label", { hasText: "leads:read" }).first().getByRole("checkbox").check();
  await card.getByRole("button", { name: "Opret nøgle" }).click();
  const err = card.locator("[role=alert]").first();
  await expect(err).toBeVisible();
  const txt = await err.innerText();
  info.attach("third-key-error.txt", { body: txt });
  expect(txt).not.toMatch(/Internal Server Error|undefined|\[object Object\]/);
  await expect(card.locator("[data-api-key]")).toHaveCount(0);
  await expect(card.locator("[data-api-key-row]")).toHaveCount(2);
});
