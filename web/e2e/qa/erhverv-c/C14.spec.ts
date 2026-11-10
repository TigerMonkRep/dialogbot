import { expect, test } from "@playwright/test";
import { SEEDED, login } from "../../helpers";
import { CSRF, campaignOwner, evid, importCsv, newCampaign, sql } from "./e2c-helpers";

/* C14 /app/campaigns/:id/contacts/:contact: "Contact history, attempts, result, permitted transcript, evidence and
   future-call suppression." Built: one row per contact (attempts, result, summary, consent as tooltip), spærreliste
   incl. automatic opt-out. Not built: contact page with history/transcript. «Nej tak» suppression: F-E2C-02 (pytest). */

test("C14 · frabedt sig opkald: står på spærrelisten, kan ikke fjernes, og nummeret springes over i næste kampagne", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const a = await newCampaign(page.request, wsId, `QA-E2C C14 A ${Date.now()}`);
  await importCsv(page.request, wsId, a.id, "Ole Berg;21222324");
  // what on_report does for «ring ikke igen» (campaigns/service.py on_report): contact opted_out + do_not_call(source=call)
  sql(`update campaign_contacts set status='opted_out', outcome='opt_out', attempts=1, summary='Bad om ikke at blive ringet op igen.' where campaign_id='${a.id}';
       insert into do_not_call (id, workspace_id, phone, reason, source, created_at) values (gen_random_uuid(), '${wsId}', '+4521222324', 'Frabad sig opkald i kampagnen', 'call', now());`);
  await page.goto(`/app/kampagner/${a.id}`);
  const row = page.locator("li").filter({ hasText: "Ole Berg" });
  await expect(row).toContainText("Vil ikke ringes op");
  await expect(row).toContainText("1 forsøg");
  await expect(row).toContainText("Bad om ikke at blive ringet op igen.");
  await expect(row.getByText(/Erhverv \(samtykke\)/)).toHaveAttribute("title", "Tilmelding på hjemmesiden, marts 2026");
  await expect(row.getByRole("button", { name: "Fjern" })).toHaveCount(0); // already called
  await page.goto("/app/kampagner");
  const dnc = page.locator("li").filter({ hasText: "+4521222324" });
  await expect(dnc).toBeVisible();
  await expect(dnc.getByRole("button", { name: "Fjern" })).toHaveCount(0);
  const entry = (await (await page.request.get(`/api/backend/workspaces/${wsId}/do-not-call`)).json()).items.find((x: { phone: string }) => x.phone === "+4521222324");
  expect((await page.request.delete(`/api/backend/workspaces/${wsId}/do-not-call/${entry.id}`, { headers: CSRF })).status()).toBe(409);
  const b = await newCampaign(page.request, wsId, `QA-E2C C14 B ${Date.now()}`);
  expect((await importCsv(page.request, wsId, b.id, "Ole Berg;+45 21 22 23 24")).blocked).toBe(1);
  await page.screenshot({ path: evid("C14", info, "spaerreliste"), fullPage: true });
});

test("C14 · roller: medarbejder kan spærre et nummer men ikke fjerne en spærring; læser kan ingenting", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  const ws = (await (await page.request.get("/api/backend/workspaces")).json())[0].id as string;
  const phone = `+4528${String(Date.now()).slice(-6)}`;
  await page.context().clearCookies();
  await login(page, SEEDED.staff);
  await page.goto("/app/kampagner");
  await page.getByLabel("Telefonnummer").fill(phone);
  await page.getByLabel("Årsag (valgfri)").fill(`QA-E2C ${info.project.name}`);
  await page.getByRole("button", { name: "Spær nummer" }).click();
  const li = page.locator("li").filter({ hasText: phone });
  await expect(li).toBeVisible();
  await expect(li.getByRole("button", { name: "Fjern" })).toHaveCount(0);
  const entry = (await (await page.request.get(`/api/backend/workspaces/${ws}/do-not-call`)).json()).items.find((x: { phone: string }) => x.phone === phone);
  expect((await page.request.delete(`/api/backend/workspaces/${ws}/do-not-call/${entry.id}`, { headers: CSRF })).status()).toBe(403);
  await page.context().clearCookies();
  await login(page, SEEDED.reader);
  expect((await page.request.post(`/api/backend/workspaces/${ws}/do-not-call`, { headers: CSRF, data: { phone: "+4529999999" } })).status()).toBe(403);
  // clean up our own entry as owner
  await page.context().clearCookies();
  await login(page, SEEDED.owner);
  expect((await page.request.delete(`/api/backend/workspaces/${ws}/do-not-call/${entry.id}`, { headers: CSRF })).ok()).toBeTruthy();
});

test("C14 · krav: kontaktside med historik, forsøg, tilladt udskrift og bevis (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C14: no /app/kampagner/[id]/[contact] route; conversation_id/next_attempt_at not in the UI; no link to transcript" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C14 side ${Date.now()}`);
  await importCsv(page.request, wsId, c.id, "Mette Hansen;20304050");
  const [x] = (await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/contacts`)).json()).items;
  await page.goto(`/app/kampagner/${c.id}`);
  const link = page.locator("li").filter({ hasText: "Mette Hansen" }).getByRole("link");
  await page.screenshot({ path: evid("C14", info, "ingen-kontaktside"), fullPage: true });
  const r = await page.goto(`/app/kampagner/${c.id}/kontakter/${x.id}`);
  expect({ link: await link.count(), status: r?.status() }).toEqual({ link: 1, status: 200 });
});
