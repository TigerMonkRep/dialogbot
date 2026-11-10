import { expect, test } from "@playwright/test";
import { campaignOwner, evid, getCampaign, newCampaign, noStaging, primaryButtons } from "./e2c-helpers";

/* C06 /app/campaigns/:id/script: "Unique manuscript upload/editor, branches, variables, personal previews and versions."
   Built: editor (opening, questions, success), «Foreslå med AI», {navn}/{virksomhed}. Not built: upload, branches,
   personal preview per contact, versions. */

test("C06 · manuskript: AI-forslag fyldes ind, gemmes, overlever reload; versionskonflikt afvises", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C06 ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  // opening + questions are empty → the AI suggestion is fetched automatically (not saved until «Gem»)
  await expect(page.getByText("Forslag fra AI er sat ind. Ret det til, og tryk Gem.")).toBeVisible();
  const opening = page.getByLabel("Første replik");
  await expect(opening).toHaveValue(/\{navn\}.*digitale assistent/);
  expect((await getCampaign(page.request, wsId, c.id)).opening).toBe("");
  await opening.fill("Hej {navn}, det er den digitale assistent fra {virksomhed}. Vi har en efterårsrabat på gulvafslibning.");
  await page.getByLabel("Spørgsmål (ét pr. linje)").fill("Hvornår har I sidst fået slebet gulvene?\n\n  Hvor mange m² drejer det sig om?  ");
  await page.getByRole("button", { name: "Gem kampagne" }).click();
  await expect(page.getByText("Gemt.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Første replik")).toHaveValue("Hej {navn}, det er den digitale assistent fra {virksomhed}. Vi har en efterårsrabat på gulvafslibning.");
  const saved = await getCampaign(page.request, wsId, c.id);
  expect(saved.questions).toEqual(["Hvornår har I sidst fået slebet gulvene?", "Hvor mange m² drejer det sig om?"]);
  // a second tab saved meanwhile → this tab's save is refused, nothing is overwritten
  const tab2 = await page.context().newPage();
  await tab2.goto(`/app/kampagner/${c.id}`);
  await tab2.getByLabel("Hvornår er kontakten interesseret?").fill("Fra fane 2");
  await tab2.getByRole("button", { name: "Gem kampagne" }).click();
  await expect(tab2.getByText("Gemt.", { exact: true })).toBeVisible();
  await page.getByLabel("Hvornår er kontakten interesseret?").fill("Fra fane 1");
  await page.getByRole("button", { name: "Gem kampagne" }).click();
  await expect(page.locator("main [role=alert]").filter({ hasText: "ændret af en anden" })).toBeVisible();
  expect((await getCampaign(page.request, wsId, c.id)).success).toBe("Fra fane 2");
  // window validation
  await page.reload();
  await page.getByLabel("Fra kl.").fill("17:00");
  await page.getByLabel("Til kl.").fill("09:00");
  await page.getByRole("button", { name: "Gem kampagne" }).click();
  await expect(page.getByText("Sluttidspunktet skal ligge efter starttidspunktet").first()).toBeVisible();
  await noStaging(page);
  await page.screenshot({ path: evid("C06", info, "manuskript"), fullPage: true });
});

test("C06 · én primær knap pr. skærm på kampagnesiden (brand.md)", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C06 knapper ${Date.now()}`, { opening: "Hej {navn}", questions: ["Hvor mange m²?"] });
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByRole("button", { name: "Start kampagne" })).toBeVisible();
  await page.screenshot({ path: evid("C06", info, "primaere-knapper"), fullPage: true });
  expect(await primaryButtons(page)).toBeLessThanOrEqual(1);
});

test("C06 · krav: upload af manuskript, forgreninger, personlig forhåndsvisning og versioner (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C06: no script upload, branches, per-contact preview or version history (CampaignEditor has plain fields)" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C06 versioner ${Date.now()}`, { opening: "Hej {navn}" });
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C06", info, "ingen-versioner"), fullPage: true });
  await expect(page.getByRole("button", { name: /version|historik|forhåndsvis/i }).or(page.getByRole("link", { name: /version|historik/i }))).toHaveCount(1, { timeout: 3_000 });
});
