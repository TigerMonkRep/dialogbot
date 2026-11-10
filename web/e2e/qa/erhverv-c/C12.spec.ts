import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { campaignOwner, evid, getCampaign, importCsv, newCampaign, noStaging, sql, stat } from "./e2c-helpers";

/* C12 /app/campaigns/:id/live: "Progress, outcomes, upcoming work, pause/resume, errors and cancel-remaining action."
   The stack has no outbound telephony, so a real start is impossible here (proved in C08). The states a dialler run
   produces are written as data on OUR OWN rows (see e2c-helpers sql()); dialler behaviour itself (pause stops calls,
   resume needs confirmation, contacts added while running) is proven in tests/qa/test_qa_e2c_campaigns.py. */

async function runningCampaign(page: Page, info: TestInfo) {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C12 ${info.project.name} ${Date.now()}`, { opening: "Hej {navn}", questions: ["Hvor mange m²?"] });
  await importCsv(page.request, wsId, c.id, "Mette Hansen;20304050\nOle Berg;21222324\nBo Lund;22334455\nJens Juul;23344556");
  sql(`update campaign_contacts set status='done', outcome='interested', attempts=1, connected_seconds=95, summary='Vil gerne have tilbud på 60 m² stuegulv.' where campaign_id='${c.id}' and name='Mette Hansen';
       update campaign_contacts set status='pending', attempts=1, next_attempt_at=now() + interval '3 hours' where campaign_id='${c.id}' and name='Ole Berg';
       update campaign_contacts set status='failed', attempts=1, error='Telefontjenesten afviste opkaldet (400)' where campaign_id='${c.id}' and name='Jens Juul';
       update campaigns set status='running', started_at=now(), version=version+1 where id='${c.id}' and workspace_id='${wsId}';`);
  return { wsId, c };
}

test("C12 · kørende kampagne: status, fremdrift = API, fejl vises, manuskript låst, pause virker og overlever reload", async ({ page }, info) => {
  const { wsId, c } = await runningCampaign(page, info);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByText("Kører", { exact: true }).first()).toBeVisible();
  const api = await getCampaign(page.request, wsId, c.id);
  expect(api.status).toBe("running");
  await expect(stat(page, "Kontakter")).toHaveText(String(api.counts.total));
  await expect(stat(page, "Talt med")).toHaveText(String(api.counts.answered));
  await expect(stat(page, "Interesserede")).toHaveText(String(api.counts.by_outcome.interested ?? 0));
  await expect(stat(page, "Tilbage")).toHaveText(String(api.counts.open));
  await expect(page.locator("li").filter({ hasText: "Jens Juul" })).toContainText("Telefontjenesten afviste opkaldet (400)");
  await expect(page.locator("li").filter({ hasText: "Mette Hansen" })).toContainText("Vil gerne have tilbud");
  await expect(page.getByText("Kampagnen kører. Sæt den på pause for at ændre manuskriptet.")).toBeVisible();
  await expect(page.getByLabel("Første replik")).toBeDisabled();
  await noStaging(page);
  await page.screenshot({ path: evid("C12", info, "koerer"), fullPage: true });
  const pause = page.getByRole("button", { name: "Sæt på pause" });
  await pause.dblclick(); // double submit is harmless
  await expect(page.getByText("På pause", { exact: true }).first()).toBeVisible();
  await page.reload();
  expect((await getCampaign(page.request, wsId, c.id)).status).toBe("paused");
  await expect(page.getByRole("heading", { name: "Genoptag kampagnen" })).toBeVisible();
  await expect(page.getByLabel("Første replik")).toBeEditable();
  // resuming requires the legal confirmation again, and is honest that outbound telephony is missing
  await expect(page.getByRole("button", { name: "Genoptag" })).toBeDisabled();
  await page.screenshot({ path: evid("C12", info, "pause"), fullPage: true });
});

test("C12 · F-E2C-03: kontakter kan ikke tilføjes til en kørende kampagne uden ny bekræftelse", async ({ page }, info) => {
  const { wsId, c } = await runningCampaign(page, info);
  const before = (await getCampaign(page.request, wsId, c.id)).counts.by_status.pending as number; // Ole + Bo, confirmed at start
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C12", info, "tilfoej-mens-koerer"), fullPage: true });
  const form = page.getByRole("button", { name: "Tilføj kontakter" });
  if (await form.count()) {
    await page.getByLabel("Eller indsæt listen").fill("Karen Kjær;24455667");
    await page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?").fill("Tilmelding på hjemmesiden, marts 2026");
    await form.click();
    await expect(page.locator("main [role=status], main [role=alert]").filter({ hasText: /tilføjet|pause|bekræft|kører/i }).first()).toBeVisible();
  }
  const after = await getCampaign(page.request, wsId, c.id);
  console.log("C12 after import:", JSON.stringify({ status: after.status, by_status: after.counts.by_status, before, form: await form.count() }));
  // either refused, or the campaign is paused for a new confirmation – never silently added to the running dial queue
  expect(after.status !== "running" || after.counts.by_status.pending === before,
    `campaign still running with ${after.counts.by_status.pending} pending contacts (${before} confirmed at start + newly added, no new confirmation)`).toBe(true);
});

test("C12 · krav: kommende opkald, live-opdatering uden reload og «annullér resten» (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C12: next_attempt_at is not in the UI type/Contact; page is server-rendered without polling; no cancel-remaining action/API" });
  const { c } = await runningCampaign(page, info);
  await page.goto(`/app/kampagner/${c.id}`);
  const upcoming = await page.locator("li").filter({ hasText: "Ole Berg" }).getByText(/næste forsøg|ringes op igen|kl\. \d/i).count();
  sql(`update campaign_contacts set status='done', outcome='callback', attempts=2 where campaign_id='${c.id}' and name='Ole Berg'`);
  const live = await expect(stat(page, "Talt med")).toHaveText("2", { timeout: 15_000 }).then(() => true, () => false);
  const cancel = await page.getByRole("button", { name: /annull|stop resten|afslut kampagnen/i }).count();
  await page.screenshot({ path: evid("C12", info, "ikke-bygget"), fullPage: true });
  console.log("C12 not built:", JSON.stringify({ upcoming, live, cancel }));
  expect({ upcoming: upcoming > 0, live, cancel: cancel > 0 }).toEqual({ upcoming: true, live: true, cancel: true });
});
