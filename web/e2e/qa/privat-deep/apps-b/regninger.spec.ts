import { expect } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat, sql } from "./pb-helpers";

/** Regninger (PC-APP-REGNINGER-01..05). The store's example («Mind mig om bilforsikringen …») is routed to a plain
 *  reminder by the fake model; the phrasing below is the one fake.py maps to add_bills. */
const SEED = "Læg regningen ind: Bilforsikring den 1. hver måned, 640 kr.";

appSuite({
  key: "regninger", sid: "PC-APP-REGNINGER", plans: "plus", seed: SEED, probe: "/bills", deletable: true,
  proveSeed: async (page, ws) => {
    await chat(page, SEED);
    const b = await (await api(page, "GET", "/bills")).json();
    expect(b.items).toHaveLength(1);
    expect(b.items[0]).toMatchObject({ name: "Bilforsikring", amount_minor: 64000, frequency: "monthly" });
    expect(sql(`select amount_minor||'/'||extract(day from next_due) from private_bills where workspace_id='${ws}'`)).toBe("64000/1");
    expect(b.month.total_minor).toBeGreaterThanOrEqual(0);
  },
  panelText: /Bilforsikring/,
  removeViaUi: async (page, ws) => {
    const a = await (await api(page, "POST", "/bills", { name: "Bilforsikring", amount: "640 kr.", due_day: 1 })).json();
    const b = await (await api(page, "POST", "/bills", { name: "Bilforsikring", amount: "700 kr.", due_day: 1 })).json();
    expect(b.id).toBe(a.id); // same name again corrects
    await api(page, "POST", "/bills", { name: "Netflix 🎬 " + "x".repeat(80), amount: "129 kr.", due_day: 5 });
    expect((await api(page, "POST", "/bills", { name: "x".repeat(101), due_day: 5 })).status()).toBe(422);
    await gotoPrivat(page, "/privat/apps/regninger");
    const panel = page.getByTestId("bills-panel");
    await expect(panel).toContainText("Netflix 🎬");
    await panel.getByRole("button", { name: "Fjern: Bilforsikring" }).click();
    // removing now asks first (ui-ux stabilt punkt 2): confirm with «Ja, fjern»
    await page.getByRole("button", { name: "Ja, fjern" }).click();
    await expect(panel).not.toContainText("Bilforsikring");
    expect(sql(`select count(*) from private_bills where workspace_id='${ws}' and name='Bilforsikring'`)).toBe("0");
    expect((await api(page, "DELETE", `/bills/${a.id}`)).status()).toBe(404);
  },
});
