import { expect, test } from "@playwright/test";
import { CSRF, campaignOwner, evid, getCampaign, importCsv, newCampaign, noStaging } from "./e2c-helpers";

/* C08 /app/campaigns/:id/quote: "Select eligible contacts, snapshot selection, package limits, clear total and terms."
   Amounts are NOT asserted (price model changes on another branch). Tested: who is included, terms/confirmation,
   start never without explicit confirmation. Snapshot of the selection: see F-E2C-03 (pytest). */

test("C08 · startboks: antal = ventende kontakter fra API, alle vilkår skal krydses af, start aldrig uden bekræftelse", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C08 ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  const start = page.getByRole("button", { name: "Start kampagne" });
  await expect(start).toBeDisabled(); // empty: no contacts
  await importCsv(page.request, wsId, c.id, "Mette Hansen;20304050\nOle Berg;21222324\nBo Lund;22334455");
  await page.request.post(`/api/backend/workspaces/${wsId}/do-not-call`, { headers: CSRF, data: { phone: "22334455" } });
  await page.reload();
  const api = await getCampaign(page.request, wsId, c.id);
  expect(api.counts.by_status).toEqual({ pending: 2, skipped: 1 });
  const box = page.locator("aside").filter({ has: page.getByText("Før den starter") });
  await expect(box.locator("h2")).toContainText(`${api.counts.by_status.pending} kontakter`);
  const list = (await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns`)).json()).legal_checklist as string[];
  const boxes = box.locator("fieldset input[type=checkbox]");
  await expect(boxes).toHaveCount(list.length);
  expect(list.join(" ")).toMatch(/sagt ja/);
  for (let i = 0; i < list.length - 1; i++) await boxes.nth(i).check();
  await expect(start).toBeDisabled(); // one box missing
  await boxes.nth(list.length - 1).check();
  // the stack has no outbound telephony: said honestly, and start stays disabled
  await expect(box.getByRole("status").filter({ hasText: /Udgående opkald er ikke sat op|ikke klar|Vælg hvilket|ikke godkendt/ })).toBeVisible();
  await expect(start).toBeDisabled();
  await noStaging(page);
  await page.screenshot({ path: evid("C08", info, "startboks"), fullPage: true });
  // direct API attempts: unconfirmed → 422, confirmed but telephony missing → 501; status stays draft
  const s = `/api/backend/workspaces/${wsId}/campaigns/${c.id}/start`;
  expect((await page.request.post(s, { headers: CSRF, data: { expected_version: api.version, legal_confirmed: false, accept_max_net_minor: api.max_cost.net_minor } })).status()).toBe(422);
  expect([409, 501]).toContain((await page.request.post(s, { headers: CSRF, data: { expected_version: api.version, legal_confirmed: true, accept_max_net_minor: api.max_cost.net_minor } })).status());
  expect((await getCampaign(page.request, wsId, c.id)).status).toBe("draft");
  // reload loses the ticks (consent is given at start time, not remembered)
  await page.reload();
  await expect(box.locator("fieldset input[type=checkbox]:checked")).toHaveCount(0);
});

test("C08 · krav: vælg hvilke kontakter der er med (udvalg) og fastfrys udvalget ved bekræftelse (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C08: all pending contacts are always included; no selection; contacts added later are dialled without re-confirmation (F-E2C-03)" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C08 udvalg ${Date.now()}`);
  await importCsv(page.request, wsId, c.id, "Mette Hansen;20304050\nOle Berg;21222324");
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.locator("li").filter({ hasText: "Mette Hansen" }).getByRole("checkbox")).toHaveCount(1, { timeout: 3_000 });
});
