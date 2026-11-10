import { expect, test } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat, pbUser, shot } from "./pb-helpers";
import { needsPrivatStack } from "../../privat/pq-helpers";

/** Ønskelister (PC-APP-OENSKELISTER-01..05). Free. Data are tasks (not deletable). Reservations are secret for the
 *  owner – asserted in the owner's UI AND the owner's API response; a guest without a subscription opens the list. */
const SEED = "Lav en ønskeliste med cykelhjelm og en god bog";

appSuite({
  key: "oenskelister", sid: "PC-APP-OENSKELISTER", plans: "free", seed: SEED, probe: "/addons", probeGated: false, deletable: false,
  proveSeed: async (page) => {
    const out = await chat(page, SEED);
    const tid = out.messages.find((m) => m.kind === "task")!.task_id!;
    const t = await (await api(page, "GET", `/tasks/${tid}`)).json();
    expect(t.items.map((i: { text: string }) => i.text)).toEqual(["Cykelhjelm", "En god bog"]);
  },
  panelText: null,
});

test.describe("ønskeliste-hemmelighed (PB)", () => {
  test.beforeEach(async ({ request }) => { test.skip(!(await needsPrivatStack(request)), "kræver Privat-stakken (:8400)"); });

  test("PC-APP-OENSKELISTER-03 gæst uden abonnement reserverer; ejer ser intet i UI eller API", async ({ page, browser }, info) => {
    await pbUser(page, info, "wish-owner", "trial");
    const tid = (await chat(page, SEED)).messages.find((m) => m.kind === "task")!.task_id!;
    const share = await (await api(page, "POST", `/tasks/${tid}/share`, { mode: "wishlist" })).json();
    expect(share.short_url).toBeTruthy();
    const guestCtx = await browser.newContext({ viewport: page.viewportSize()! });
    const guest = await guestCtx.newPage();
    // the invitation page asks for a FREE private account (no subscription) – that is the rule's «uden abonnement»
    await guest.goto(new URL(share.short_url).pathname);
    await expect(guest.getByRole("button", { name: "Åbn listen" })).toBeVisible({ timeout: 20_000 });
    await shot(guest, info, "PC-APP-OENSKELISTER-03", "guest-invite");
    const g = await pbUser(guest, info, "wish-guest", "none");
    expect((await (await guest.request.get("/api/backend/privat/subscription")).json()).entitled).toBeFalsy();
    await guest.goto(new URL(share.short_url).pathname);
    await guest.getByRole("button", { name: "Åbn listen" }).click();
    await expect(guest.getByText("Cykelhjelm").first()).toBeVisible({ timeout: 20_000 });
    await shot(guest, info, "PC-APP-OENSKELISTER-03", "guest-list");
    test.info().annotations.push({ type: "guest-ws", description: g.ws });
    const reserve = guest.getByRole("button", { name: /Reservér|Jeg køber|Jeg giver/i }).first();
    const canReserve = (await reserve.count()) > 0;
    if (canReserve) { await reserve.click(); await guest.waitForTimeout(1500); }
    await guestCtx.close();
    const owner = JSON.stringify(await (await api(page, "GET", `/tasks/${tid}`)).json()).toLowerCase();
    expect(owner).not.toMatch(/reserved_by|pledged_by|reserveret af|"reserved":\s*true/);
    await gotoPrivat(page, `/privat/opgaver/${tid}`);
    await expect(page.getByText(/reserveret/i)).toHaveCount(0);
    await shot(page, info, "PC-APP-OENSKELISTER-03", "owner");
    test.info().annotations.push({ type: "guest-reserve-button", description: String(canReserve) });
  });
});
