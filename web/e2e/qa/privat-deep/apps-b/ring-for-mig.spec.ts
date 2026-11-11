import { expect, test } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat, pbUser, shot, sql } from "./pb-helpers";
import { dialled, needsPrivatStack, QA_API } from "../../privat/pq-helpers";

/** Ring for mig (PC-APP-RING-FOR-MIG-01..05). Included in ALL plans (Basis too) – F-PB-02 covers the texts that say
 *  «Plus og Familie». Calls only after explicit approval: asserted on :8400/__qa/calls (what would have been dialled)
 *  and private_calls, never a real call (fake Vapi, socket guard). */
const SEED = "Ring til Cykelværkstedet på 70 20 30 40 og find en tid torsdag efter klokken tre";

appSuite({
  key: "ring-for-mig", sid: "PC-APP-RING-FOR-MIG", plans: "all", seed: SEED, probe: "/businesses/search?q=frisør", deletable: false,
  proveSeed: async (page, ws, email) => {
    expect((await page.request.post(`${QA_API}/__qa/phone-verified`, { data: { email } })).ok()).toBeTruthy();
    const before = (await dialled(page.request)).length;
    const out = await chat(page, SEED);
    const tid = out.messages.find((m) => m.task_id)?.task_id;
    expect(tid, JSON.stringify(out)).toBeTruthy();
    expect(sql(`select count(*) from private_calls where workspace_id='${ws}' and vapi_call_id is not null`)).toBe("0");
    expect((await dialled(page.request)).length, "intet ringet før godkend").toBe(before);
  },
  panelText: null,
});

/** The task page shows «Næste skridt: Godkend opkaldet» + «Se forslaget og godkend», which opens the proposal. */
async function openProposal(page: import("@playwright/test").Page) {
  const see = page.getByRole("button", { name: "Se forslaget og godkend" });
  const direct = page.getByRole("button", { name: /^Godkend/ });
  await expect(see.or(direct).first()).toBeVisible({ timeout: 20_000 });
  if (await see.isVisible()) await see.click();
}

test.describe("ring-for-mig godkendelse (PB)", () => {
  test.beforeEach(async ({ request }) => { test.skip(!(await needsPrivatStack(request)), "kræver Privat-stakken (:8400)"); });

  test("PC-APP-RING-FOR-MIG-03 forslag → «Godkend opkald» er eneste vej til et opkald; afvis ringer aldrig", async ({ page }, info) => {
    const { ws, email } = await pbUser(page, info, "rfm-approve", "trial");
    expect((await page.request.post(`${QA_API}/__qa/phone-verified`, { data: { email } })).ok()).toBeTruthy();
    const before = (await dialled(page.request)).length;
    // decline path
    const a = (await chat(page, SEED)).messages.find((m) => m.task_id)!.task_id!;
    await gotoPrivat(page, `/privat/opgaver/${a}`);
    await openProposal(page);
    await expect(page.getByRole("button", { name: /^Godkend/ })).toBeVisible();
    await shot(page, info, "PC-APP-RING-FOR-MIG-03", "proposal");
    await page.getByRole("button", { name: "Afvis" }).click();
    await page.waitForTimeout(1500);
    expect((await dialled(page.request)).length).toBe(before);
    // approve path
    const b = (await chat(page, SEED)).messages.find((m) => m.task_id)!.task_id!;
    await gotoPrivat(page, `/privat/opgaver/${b}`);
    await openProposal(page);
    const biz = page.getByLabel(/virksomhed/i);
    if (await biz.count()) await biz.check();
    const res = page.waitForResponse((r) => r.url().includes(`/calls/${b}/approve`));
    await page.getByRole("button", { name: /^Godkend/ }).click();
    expect((await res).ok()).toBeTruthy();
    // dialled now (inside calling hours) or planned for when they open – either way only after the approval
    await expect.poll(async () => (await dialled(page.request)).length > before
      || sql(`select status from private_tasks where id='${b}'`) === "planned", { timeout: 20_000 }).toBeTruthy();
    expect(sql(`select count(*) from private_calls where workspace_id='${ws}' and task_id='${a}' and vapi_call_id is not null`)).toBe("0");
    await shot(page, info, "PC-APP-RING-FOR-MIG-03", "approved");
  });

  test("PC-APP-RING-FOR-MIG-02 uden plan: plan-arket nævner Basis (F-PB-02)", async ({ page }, info) => {
    await pbUser(page, info, "rfm-noplan", "none");
    await gotoPrivat(page, "/privat/butik/ring-for-mig");
    await page.getByTestId("needs-plan").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("radio", { name: /Basis/ })).toBeVisible();
    await shot(page, info, "PC-APP-RING-FOR-MIG-02", "plansheet-text");
    await expect.soft(dialog.getByText(/er med i Plus og Familie/), "F-PB-02: Ring for mig er med i alle planer").toHaveCount(0);
    const r = await api(page, "POST", "/addons/ring-for-mig/enable");
    expect.soft((await r.json()).message, "F-PB-02").not.toContain("Plus og Familie");
  });
});
