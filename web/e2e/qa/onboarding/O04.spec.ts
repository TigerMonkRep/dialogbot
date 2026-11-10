import { expect, test } from "@playwright/test";
import { freshOwner, skipSetupGate } from "../../helpers";
import { BASE, CSRF, api, colleague, completeProfile, snap } from "./e2b";

/* QA O04 (E2B) – /onboarding/languages → trin 1 «Sprog over for jeres kunder» + «Den taler»-chips.
 * Krav: "Interface, default conversation, enabled conversation and report languages; voice preview."
 * Kilde: web/src/app/opsaetning/1/step1.tsx:43-48,87-92,223-226,261-265,294-302. */
const ID = "O04";

test("O04 · hovedsprog og ekstra sprog gemmes, hovedsproget kan ikke fravælges, overlever reload", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  const sel = page.getByLabel("Sprog over for jeres kunder");
  await expect(sel).toHaveValue("da");
  await expect(page.getByRole("button", { name: "Dansk", exact: true })).toBeDisabled(); // primary cannot be removed
  await page.getByRole("button", { name: "+ Tysk" }).click();
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await expect.poll(async () => (await api(page).get(`/workspaces/${wsId}/languages`)).body).toMatchObject({ default_conversation_language: "da", enabled_conversation_languages: ["da", "de"] });
  await sel.selectOption("en");
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await expect.poll(async () => (await api(page).get(`/workspaces/${wsId}/languages`)).body.default_conversation_language).toBe("en");
  const l = (await api(page).get(`/workspaces/${wsId}/languages`)).body;
  expect(l.enabled_conversation_languages[0]).toBe("en");
  await page.reload();
  await expect(page.getByLabel("Sprog over for jeres kunder")).toHaveValue("en");
  await expect(page.getByRole("button", { name: "Engelsk", exact: true })).toBeDisabled();
  await snap(page, ID, info, "sprog");
});

test("O04 · at ÅBNE trin 1 i en browser på engelsk må ikke stille kundesproget om (ingen skjulte ændringer ved visning)", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  expect((await api(page).get(`/workspaces/${wsId}/languages`)).body.default_conversation_language).toBe("da");
  // A colleague (staff) whose browser is English opens trin 1 and only looks.
  const staff = await colleague(page, browser, info, wsId, "staff");
  await staff.ctx.close();
  const ctx = await browser.newContext({ baseURL: BASE, locale: "en-GB", extraHTTPHeaders: { "accept-language": "en-GB,en;q=0.9" }, viewport: info.project.use.viewport ?? undefined });
  const p = await ctx.newPage();
  await p.request.post("/api/auth/login", { headers: CSRF, data: { email: staff.email, password: process.env.SEED_DEMO_PASSWORD ?? "E2e-Demo-Password-2026" } });
  await p.request.post("/api/auth/workspace", { headers: CSRF, data: { workspace_id: wsId } });
  await skipSetupGate(p);
  await p.goto("/opsaetning/1");
  await expect(p.locator("main")).toBeVisible();
  await p.waitForTimeout(2500);
  await snap(p, ID, info, "engelsk-browser");
  const after = (await api(page).get(`/workspaces/${wsId}/languages`)).body;
  await ctx.close();
  expect(after.default_conversation_language, "Peter taler nu engelsk til danske kunder, fordi en kollega åbnede siden på en engelsk browser").toBe("da");
});

test("O04 · krav: rapportsprog og stemmeprøve i sprogvalget", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  const reportCtl = await page.getByLabel(/Rapport/i).count();
  await page.goto("/opsaetning/3");
  const hear = await page.getByRole("button", { name: /^Hør / }).count();
  test.info().annotations.push({ type: "gap", description: `rapportsprog-kontrol: ${reportCtl}; «Hør»-knapper i trin 3: ${hear}` });
  const l = (await api(page).get(`/workspaces/${wsId}/languages`)).body;
  expect(l.report_language).toBeTruthy();
  expect.soft(hear, "ingen «Hør»-knap i trin 3, selvom teksten lover en prøvetone (simuleret motor uden prøver)").toBeGreaterThan(0);
  expect.soft(reportCtl, "rapportsprog kan ikke vælges (siden siger «Rapporter … er altid på dansk»)").toBeGreaterThan(0);
});
