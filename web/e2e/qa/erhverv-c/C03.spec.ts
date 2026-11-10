import { expect, test } from "@playwright/test";
import { campaignOwner, evid, getCampaign, newCampaign, noStaging } from "./e2c-helpers";

/* C03 /app/campaigns/:id/source: "File upload, API or supported read-only database source; preview and connection
   states." Built: CSV file upload / paste. Not built: API source, read-only database source, connection states. */

test("C03 · CSV-fil uploades i browseren, kontakterne gemmes og overlever reload", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C03 ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByText("Ingen kontakter endnu.")).toBeVisible(); // empty state
  const submit = page.getByRole("button", { name: "Tilføj kontakter" });
  await expect(submit).toBeDisabled();
  // Excel-style CSV with BOM, semicolons and a header row
  const csv = "﻿Navn;Telefon;Firma;E-mail\r\nMette Hansen;20 30 40 50;Hansen Byg ApS;mette@hansenbyg.example\r\nOle Berg;+45 21 22 23 24;Berg VVS;\r\n";
  await page.getByLabel("CSV-fil").setInputFiles({ name: "kunder.csv", mimeType: "text/csv", buffer: Buffer.from(csv, "utf8") });
  // the file's content is shown before import (preview)
  await expect(page.getByLabel("Eller indsæt listen")).toHaveValue(/Mette Hansen;20 30 40 50/);
  await page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?").fill("Tilmelding på hjemmesiden, marts 2026");
  await submit.click();
  await expect(page.getByText("2 kontakter tilføjet")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Mette Hansen", { exact: true })).toBeVisible();
  await expect(page.getByText("+4521222324")).toBeVisible();
  const items = (await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/contacts`)).json()).items;
  expect(items.map((x: { name: string; company: string; phone: string; email: string | null }) => [x.name, x.company, x.phone, x.email])).toEqual([
    ["Mette Hansen", "Hansen Byg ApS", "+4520304050", "mette@hansenbyg.example"], ["Ole Berg", "Berg VVS", "+4521222324", null]]);
  expect((await getCampaign(page.request, wsId, c.id)).counts.total).toBe(2);
  await noStaging(page);
  await page.screenshot({ path: evid("C03", info, "csv-importeret"), fullPage: true });
});

test("C03 · serverfejl ved import: fejlen vises, intet importeres, listen bevares", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C03 500 ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await page.route("**/contacts/import", (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Noget gik galt hos os. Prøv igen.", request_id: "qa-e2c" }) }));
  await page.getByLabel("Eller indsæt listen").fill("Mette Hansen;20304050");
  await page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?").fill("Tilmelding på hjemmesiden, marts 2026");
  await page.getByRole("button", { name: "Tilføj kontakter" }).click();
  await expect(page.locator("main [role=alert]").filter({ hasText: "Noget gik galt" })).toBeVisible();
  await expect(page.getByLabel("Eller indsæt listen")).toHaveValue("Mette Hansen;20304050");
  expect((await getCampaign(page.request, wsId, c.id)).counts.total).toBe(0);
});

test("C03 · krav: API-kilde eller skrivebeskyttet database som kontaktkilde med forbindelsesstatus (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C03: only CSV upload/paste exists (kampagner/client.tsx ImportContacts); no API/database source or connection state" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C03 kilde ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C03", info, "kun-csv"), fullPage: true });
  await expect(page.getByRole("radio", { name: /API|database/i }).or(page.getByRole("button", { name: /API|database|forbind/i }))).toHaveCount(1, { timeout: 3_000 });
});
