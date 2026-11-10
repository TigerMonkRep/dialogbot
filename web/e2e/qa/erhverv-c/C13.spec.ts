import { expect, test } from "@playwright/test";
import { CSRF, campaignOwner, evid, getCampaign, importCsv, newCampaign, noStaging, sql, stat } from "./e2c-helpers";

/* C13 /app/campaigns/:id/results: "Final outcomes, follow-up, export, final report and delivery status."
   Built: outcome counters and per-contact outcome/summary, lead link for follow-up (dialler side in pytest).
   Not built: export, final report, delivery status. */

async function completed(page: import("@playwright/test").Page, info: import("@playwright/test").TestInfo) {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C13 ${info.project.name} ${Date.now()}`, { opening: "Hej {navn}", questions: ["x"] });
  await importCsv(page.request, wsId, c.id, "Mette Hansen;20304050\nOle Berg;21222324\nBo Lund;22334455\nKaren Kjær;24455667");
  sql(`update campaign_contacts set status='done', outcome='interested', attempts=1, summary='Vil have tilbud.' where campaign_id='${c.id}' and name='Mette Hansen';
       update campaign_contacts set status='opted_out', outcome='opt_out', attempts=1, summary='Vil ikke ringes op.' where campaign_id='${c.id}' and name='Ole Berg';
       update campaign_contacts set status='no_answer', outcome='no_answer', attempts=2 where campaign_id='${c.id}' and name='Bo Lund';
       update campaign_contacts set status='done', outcome='callback', attempts=2, summary='Ring efter kl. 16.' where campaign_id='${c.id}' and name='Karen Kjær';
       update campaigns set status='completed', started_at=now() - interval '1 day', completed_at=now(), version=version+1 where id='${c.id}' and workspace_id='${wsId}';`);
  return { wsId, c };
}

test("C13 · afsluttet kampagne: udfald pr. kontakt, tællere = API, kan ikke genstartes eller få nye kontakter", async ({ page }, info) => {
  const { wsId, c } = await completed(page, info);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByText("Kampagnen er afsluttet: alle kontakter er ringet op.")).toBeVisible();
  const api = await getCampaign(page.request, wsId, c.id);
  expect(api.counts.answered).toBe(3); // done ×2 + opted_out (F-EB-02 fixed)
  await expect(stat(page, "Kontakter")).toHaveText("4");
  await expect(stat(page, "Talt med")).toHaveText(String(api.counts.answered));
  await expect(stat(page, "Interesserede")).toHaveText("1");
  await expect(stat(page, "Ring tilbage")).toHaveText("1");
  await expect(stat(page, "Intet svar")).toHaveText("1");
  await expect(stat(page, "Tilbage")).toHaveText("0");
  for (const [who, label] of [["Mette Hansen", "Interesseret"], ["Ole Berg", "Vil ikke ringes op"], ["Bo Lund", "Intet svar"], ["Karen Kjær", "Ring tilbage"]]) {
    await expect(page.locator("li").filter({ hasText: who })).toContainText(label);
  }
  await expect(page.getByRole("button", { name: "Tilføj kontakter" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Start kampagne|Genoptag/ })).toHaveCount(0);
  await expect(page.getByLabel("Første replik")).toBeDisabled();
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/start`, { headers: CSRF, data: { expected_version: api.version, legal_confirmed: true, accept_max_net_minor: 10 ** 9 } })).status()).toBe(409);
  await noStaging(page);
  await page.screenshot({ path: evid("C13", info, "afsluttet"), fullPage: true });
  // the list page agrees
  await page.goto("/app/kampagner");
  const row = page.locator("li").filter({ hasText: c.name });
  await expect(row).toContainText("Afsluttet");
  await expect(row).toContainText(`${api.counts.answered} talt med`);
  await expect(row).toContainText("1 interesserede");
  await expect(row).toContainText("0 tilbage");
});

test("C13 · krav: eksport, slutrapport og leveringsstatus (ikke bygget)", async ({ page }, info) => {
  test.fail(true, "C13: not-implemented – eksport, slutrapport og leveringsstatus");
  test.info().annotations.push({ type: "not-implemented", description: "C13: no export, final report or delivery status on the campaign page or API" });
  const { c } = await completed(page, info);
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C13", info, "ingen-eksport"), fullPage: true });
  await expect(page.getByRole("button", { name: /eksport|download|rapport/i }).or(page.getByRole("link", { name: /eksport|download|rapport/i }))).toHaveCount(1, { timeout: 3_000 });
});
