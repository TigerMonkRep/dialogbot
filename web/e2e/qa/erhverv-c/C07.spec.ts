import { expect, test } from "@playwright/test";
import { campaignOwner, evid, getCampaign, newCampaign } from "./e2c-helpers";

/* C07 /app/campaigns/:id/test: "Simulated call tests, missing-variable examples, issue review and approval."
   Nothing of this is built; the dialler side of an unknown variable is proven in tests/qa/test_qa_e2c_campaigns.py. */

test("C07 · F-E2C-04: ukendt variabel i første replik ({fornavn}) afvises eller advares om, før den kan blive sagt højt", async ({ page }, info) => {
  test.fail(true, "F-E2C-04-C07: S2 new – Ukendte variabler i første replik ({fornavn}, {firma}, {Navn}) gemmes uden advarsel og læses …");
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C07 ${Date.now()}`, { opening: "Hej", questions: ["x"] });
  await page.goto(`/app/kampagner/${c.id}`);
  await page.getByLabel("Første replik").fill("Hej {fornavn}, det er den digitale assistent fra {firma}.");
  await page.getByRole("button", { name: "Gem kampagne" }).click();
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: evid("C07", info, "ukendt-variabel"), fullPage: true });
  const saved = (await getCampaign(page.request, wsId, c.id)).opening as string;
  const warned = await page.locator("main [role=alert]").filter({ hasText: /fornavn|variabel|ukendt/i }).count();
  expect(warned > 0 || !saved.includes("{fornavn}"), `saved opening ${JSON.stringify(saved)} without any warning`).toBe(true);
});

test("C07 · krav: simuleret testopkald med eksempler på manglende variabler og godkendelse (ikke bygget)", async ({ page }, info) => {
  test.fail(true, "C07: not-implemented – simuleret testopkald med manglende variabler og godkendelse");
  test.info().annotations.push({ type: "not-implemented", description: "C07: no simulated call test on the campaign; setup check campaign.test_call needs a real answered call" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C07 test ${Date.now()}`, { opening: "Hej {navn}" });
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C07", info, "intet-testopkald"), fullPage: true });
  await expect(page.getByRole("button", { name: /test|prøv|simul|hør/i })).toHaveCount(1, { timeout: 3_000 });
});
