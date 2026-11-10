import { expect, test } from "@playwright/test";
import { DEMO_PASSWORD, SEEDED, freshOwner, login } from "../../helpers";
import { CSRF, campaignOwner, evid, getCampaign, newCampaign, noStaging } from "./e2c-helpers";

/* C02 /app/campaigns/new (→ /app/kampagner): "Campaign name, purpose, intended outcome and language choice." (DB-008) */

test("C02 · opret kampagne i browseren: navn + formål gemmes via API, overlever reload, ét klik = én kampagne", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  await page.goto("/app/kampagner");
  await expect(page.getByRole("heading", { name: "Ny kampagne" })).toBeVisible();
  await noStaging(page);
  const create = page.getByRole("button", { name: "Opret kampagne" });
  await expect(create).toBeDisabled(); // empty name
  await page.getByLabel("Navn på kampagnen").fill("   ");
  await expect(create).toBeDisabled(); // whitespace only
  const name = `QA-E2C C02 ${info.project.name} ${Date.now()}`;
  await page.getByLabel("Navn på kampagnen").fill(name);
  await page.getByLabel("Hvad skal opkaldet handle om?").fill("Tilbyde gulvafslibning til tidligere kunder inden jul");
  await create.dblclick(); // double submit
  await page.waitForURL(/\/app\/kampagner\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").pop()!;
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Kladde", { exact: true }).first()).toBeVisible();
  const list = (await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns`)).json()).items as { name: string }[];
  expect(list.filter((c) => c.name === name)).toHaveLength(1);
  const c = await getCampaign(page.request, wsId, id);
  expect([c.status, c.purpose]).toEqual(["draft", "Tilbyde gulvafslibning til tidligere kunder inden jul"]);
  // intended outcome («Hvornår er kontakten interesseret?») is set in the editor and survives reload
  const success = page.getByLabel("Hvornår er kontakten interesseret?");
  await expect(success).toBeEditable();
  await success.fill("Kunden vil have et uforpligtende tilbud på afslibning");
  await page.getByRole("button", { name: "Gem kampagne" }).click();
  await expect(page.getByText("Gemt.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Hvornår er kontakten interesseret?")).toHaveValue("Kunden vil have et uforpligtende tilbud på afslibning");
  expect((await getCampaign(page.request, wsId, id)).success).toBe("Kunden vil have et uforpligtende tilbud på afslibning");
  await noStaging(page);
  await page.screenshot({ path: evid("C02", info, "oprettet"), fullPage: true });
});

test("C02 · F-E2C-01: kunde der kun har valgt kampagner kan slå udgående opkald til og oprette en kampagne", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info, "campaigns");
  await page.goto("/app/kampagner");
  const enable = page.getByRole("button", { name: "Ja, slå udgående opkald til" });
  if (await enable.count()) {
    await enable.click();
    await page.waitForLoadState("networkidle");
  }
  await page.screenshot({ path: evid("C02", info, "kun-kampagner-kan-ikke-slaa-til"), fullPage: true });
  await expect(page.locator("main [role=alert]")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Ny kampagne" })).toBeVisible();
  expect((await (await page.request.get(`/api/backend/workspaces/${wsId}/goals`)).json()).product_intent).toBe("campaigns");
});

test("C02 · serverfejl (500) ved oprettelse vises ærligt, og der oprettes intet", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  await page.goto("/app/kampagner");
  await page.route("**/api/backend/workspaces/*/campaigns", (r) => r.request().method() === "POST"
    ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Noget gik galt hos os. Prøv igen.", request_id: "qa-e2c-500" }) })
    : r.continue());
  await page.getByLabel("Navn på kampagnen").fill(`QA-E2C 500 ${Date.now()}`);
  await page.getByRole("button", { name: "Opret kampagne" }).click();
  await expect(page.locator("main [role=alert]").filter({ hasText: "Noget gik galt hos os" })).toBeVisible();
  await expect(page).toHaveURL(/\/app\/kampagner$/);
  await expect(page.getByLabel("Navn på kampagnen")).not.toHaveValue(""); // what the user typed is kept
  expect((await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns`)).json()).items).toHaveLength(0);
});

test("C02 · udløbet session: oprettelse afvises, intet oprettes", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  await page.goto("/app/kampagner");
  await page.getByLabel("Navn på kampagnen").fill(`QA-E2C udløbet ${Date.now()}`);
  const cookies = await page.context().cookies();
  await page.context().clearCookies();
  await page.getByRole("button", { name: "Opret kampagne" }).click();
  await expect.poll(async () => page.url().includes("/login") || await page.locator("main [role=alert]").count() > 0, { timeout: 10_000 }).toBe(true);
  await page.screenshot({ path: evid("C02", info, "session-udloebet"), fullPage: true });
  await page.context().addCookies(cookies);
  expect((await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns`)).json()).items).toHaveLength(0);
});

test("C02 · roller: medarbejder ser kampagner men kan ikke oprette; læser ser dem ikke; API afviser", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  const ws = (await (await page.request.get("/api/backend/workspaces")).json())[0].id as string;
  const c = await newCampaign(page.request, ws, `QA-E2C rolle ${info.project.name} ${Date.now()}`);
  await page.context().clearCookies();
  await login(page, SEEDED.staff);
  await page.goto("/app/kampagner");
  await expect(page.getByText("Kun administratorer og ejere kan oprette og starte kampagner.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Opret kampagne" })).toHaveCount(0);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByRole("heading", { name: c.name })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start kampagne" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Tilføj kontakter" })).toHaveCount(0);
  await expect(page.getByLabel("Hvornår er kontakten interesseret?")).toBeDisabled();
  expect((await page.request.post(`/api/backend/workspaces/${ws}/campaigns`, { headers: CSRF, data: { name: "x" } })).status()).toBe(403);
  await page.screenshot({ path: evid("C02", info, "medarbejder"), fullPage: true });
  await page.context().clearCookies();
  await login(page, SEEDED.reader);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByText("Kampagner kan ses af medarbejdere, administratorer og ejere.")).toBeVisible();
  await expect(page.getByRole("heading", { name: c.name })).toHaveCount(0);
  expect((await page.request.get(`/api/backend/workspaces/${ws}/campaigns/${c.id}`)).status()).toBe(403);
  void DEMO_PASSWORD;
});

test("C02 · krav: sprogvalg for kampagnen (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C02 language choice: no field in UI (client.tsx NewCampaign/CampaignEditor) or API (CampaignIn)" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C sprog ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C02", info, "intet-sprogvalg"), fullPage: true });
  await expect(page.getByLabel(/sprog/i)).toHaveCount(1);
});
