import { expect, test } from "@playwright/test";
import { CSRF, campaignOwner, evid, getCampaign, importCsv, newCampaign, stat } from "./e2c-helpers";

/* C05 /app/campaigns/:id/validation: "Eligible/excluded rows, corrections, deduplication, suppression and error export."
   Built: counts for added/duplicates/blocked/invalid (+ first 5 row numbers), spærreliste, remove contact.
   Not built: correcting a row, error export. */

test("C05 · import viser tilføjet/dubletter/spærret/ugyldige; tællere = API; spærring fra spærrelisten virker", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C05 ${Date.now()}`);
  // block Ole via the UI's spærreliste first
  await page.goto("/app/kampagner");
  await page.getByLabel("Telefonnummer").fill("21 22 23 24");
  await page.getByLabel("Årsag (valgfri)").fill("Bad os lade være");
  await page.getByRole("button", { name: "Spær nummer" }).click();
  await expect(page.getByText("+4521222324")).toBeVisible();
  await page.goto(`/app/kampagner/${c.id}`);
  await page.getByLabel("Eller indsæt listen").fill("Navn;Telefon;Firma\nMette Hansen;20 30 40 50;Hansen Byg ApS\nOle Berg;21222324;Berg VVS\nForkert;123;X\nMette igen;0045 20304050;Dup");
  await page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?").fill("Tilmelding på hjemmesiden, marts 2026");
  const submit = page.getByRole("button", { name: "Tilføj kontakter" });
  await submit.click();
  const msg = page.locator("main [role=status]").filter({ hasText: "kontakter tilføjet" });
  await expect(msg).toContainText("1 kontakter tilføjet");
  await expect(msg).toContainText("1 fandtes allerede");
  await expect(msg).toContainText("1 står på spærrelisten");
  await expect(msg).toContainText("1 ugyldige numre");
  await page.screenshot({ path: evid("C05", info, "validering"), fullPage: true });
  // the same list again (refresh / double submit): nothing new
  await page.getByLabel("Eller indsæt listen").fill("Mette Hansen;20304050");
  await submit.click();
  await expect(page.locator("main [role=status]").filter({ hasText: "kontakter tilføjet" })).toContainText("0 kontakter tilføjet, 1 fandtes allerede");
  await page.reload();
  const api = await getCampaign(page.request, wsId, c.id);
  expect(api.counts.total).toBe(1);
  await expect(stat(page, "Kontakter")).toHaveText(String(api.counts.total));
  await expect(stat(page, "Tilbage")).toHaveText(String(api.counts.open));
  // remove the contact: counters follow
  await page.getByRole("button", { name: "Fjern" }).first().click();
  await expect(page.getByText("Ingen kontakter endnu.")).toBeVisible();
  expect((await getCampaign(page.request, wsId, c.id)).counts.total).toBe(0);
});

test("C05 · spærring af et nummer efter import springer den ventende kontakt over", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C05 spær ${Date.now()}`);
  await importCsv(page.request, wsId, c.id, "Mette Hansen;20304050\nOle Berg;21222324");
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/do-not-call`, { headers: CSRF, data: { phone: "+45 21222324" } })).status()).toBe(201);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.locator("li").filter({ hasText: "Ole Berg" }).getByText("Spærret")).toBeVisible();
  const api = await getCampaign(page.request, wsId, c.id);
  expect(api.counts.by_status).toEqual({ pending: 1, skipped: 1 });
  await expect(stat(page, "Tilbage")).toHaveText("1");
});

test("C05 · alle importerede kontakter kan ses (501 kontakter: tæller og liste stemmer)", async ({ page }, info) => {
  test.fail(true, "F-E2C-10-C05: S3 new – Kampagnesiden viser højst 500 kontakter uden «vis flere»: ved 501 kontakter siger tælleren 501, …");
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C05 501 ${Date.now()}`);
  const rows = Array.from({ length: 501 }, (_, i) => `Kontakt ${i + 1};${String(30000000 + i)}`).join("\n");
  expect((await importCsv(page.request, wsId, c.id, rows)).added).toBe(501);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(stat(page, "Kontakter")).toHaveText("501");
  await page.screenshot({ path: evid("C05", info, "501-kontakter"), fullPage: false });
  const shown = await page.locator("li").filter({ hasText: /^Kontakt \d+/ }).count();
  const more = await page.getByRole("button", { name: /vis flere|se alle|næste/i }).count();
  expect(shown === 501 || more > 0, `list shows ${shown} of 501 contacts and offers no way to see the rest`).toBe(true);
});

test("C05 · krav: ret en ugyldig række og eksportér fejl (ikke bygget)", async ({ page }, info) => {
  test.fail(true, "C05: not-implemented – ret ugyldig række og eksportér fejl");
  test.info().annotations.push({ type: "not-implemented", description: "C05: no correction of invalid rows, no error export; only the first 5 row numbers in a status line" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C05 eksport ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await page.getByLabel("Eller indsæt listen").fill("Forkert;123");
  await page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?").fill("Tilmelding på hjemmesiden, marts 2026");
  await page.getByRole("button", { name: "Tilføj kontakter" }).click();
  await expect(page.locator("main [role=status]").filter({ hasText: "ugyldige" })).toBeVisible();
  await page.screenshot({ path: evid("C05", info, "ingen-eksport"), fullPage: true });
  await expect(page.getByRole("button", { name: /eksport|download|hent fejl/i }).or(page.getByRole("link", { name: /eksport|download/i }))).toHaveCount(1, { timeout: 3_000 });
});
