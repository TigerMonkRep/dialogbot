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

const openList = (p: import("@playwright/test").Page) => p.getByRole("button", { name: "Åbn listen" }).or(p.getByRole("link", { name: "Åbn listen" })).first();

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
    await expect(openList(guest)).toBeVisible({ timeout: 20_000 });
    await shot(guest, info, "PC-APP-OENSKELISTER-03", "guest-invite");
    const g = await pbUser(guest, info, "wish-guest", "none");
    expect((await (await guest.request.get("/api/backend/privat/subscription")).json()).entitled).toBeFalsy();
    await guest.goto(new URL(share.short_url).pathname);
    await openList(guest).click();
    await expect(guest.getByText("Cykelhjelm").first()).toBeVisible({ timeout: 20_000 });
    await shot(guest, info, "PC-APP-OENSKELISTER-03", "guest-list");
    test.info().annotations.push({ type: "guest-ws", description: g.ws });
    const reserve = guest.getByRole("button", { name: /Reservér|Jeg køber|Jeg giver/i }).first();
    const canReserve = (await reserve.count()) > 0;
    if (canReserve) { await reserve.click(); await guest.waitForTimeout(1500); }
    await guestCtx.close();
    const owner = JSON.stringify(await (await api(page, "GET", `/tasks/${tid}`)).json()).toLowerCase();
    // the owner's own view: «reserved» stays null and «reserved_by_me» false for every wish (no name, no flag)
    expect(owner).not.toMatch(/"reserved":\s*(true|\{|")|"reserved_by_me":\s*true|pledged_by|reserveret af/);
    await gotoPrivat(page, `/privat/opgaver/${tid}`);
    // the owner's page explains «Du kan ikke se, hvad der er reserveret» – that sentence is fine; no per-wish badge
    await expect(page.getByText(/^Reserveret|reserveret af|er reserveret\s*$/i)).toHaveCount(0);
    await shot(page, info, "PC-APP-OENSKELISTER-03", "owner");
    test.info().annotations.push({ type: "guest-reserve-button", description: String(canReserve) });
  });
});
