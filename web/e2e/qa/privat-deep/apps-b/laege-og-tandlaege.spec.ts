import { expect } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat, sql } from "./pb-helpers";
import { dialled, QA_API } from "../../privat/pq-helpers";

/** Læge & tandlæge (PC-APP-LAEGE-OG-TANDLAEGE-01..05). Booking needs a saved clinic first; then a call PROPOSAL –
 *  nothing is dialled (GET :8400/__qa/calls) before the user approves. */
const SAVE = "Gem min tandlæge, den hedder Smil Klinikken, nummer 86 12 34 56";
const BOOK = "Book et tandeftersyn hos min tandlæge – helst en morgen i næste måned";

appSuite({
  key: "laege-og-tandlaege", sid: "PC-APP-LAEGE-OG-TANDLAEGE", plans: "plus", seed: SAVE, probe: "/health-contacts", deletable: true,
  proveSeed: async (page, ws, email) => {
    expect((await page.request.post(`${QA_API}/__qa/phone-verified`, { data: { email, phone: "+4520304050" } })).ok()).toBeTruthy();
    await chat(page, BOOK);
    expect(sql(`select count(*) from private_calls where workspace_id='${ws}'`), "ingen opkald uden gemt klinik").toBe("0");
    await chat(page, SAVE);
    const hc = (await (await api(page, "GET", "/health-contacts")).json()).items;
    expect(hc).toHaveLength(1);
    expect(hc[0].name).toBe("Smil Klinikken");
    const before = (await dialled(page.request)).length;
    await chat(page, BOOK);
    expect(Number(sql(`select count(*) from private_calls where workspace_id='${ws}'`))).toBeLessThanOrEqual(1);
    expect((await dialled(page.request)).length, "intet ringet før godkendelse").toBe(before);
    const data = sql(`select data::text from private_app_data where workspace_id='${ws}' and app_key='laege-og-tandlaege'`);
    expect(Object.keys(JSON.parse(data)).every((k) => ["tandlaege", "laege", "reminded"].includes(k)), data).toBeTruthy();
  },
  panelText: /Smil Klinikken/,
  removeViaUi: async (page) => {
    await api(page, "POST", "/messages", { text: SAVE });
    await gotoPrivat(page, "/privat/apps/laege-og-tandlaege");
    const panel = page.getByTestId("health-panel");
    await expect(panel).toContainText("Smil Klinikken");
    await panel.getByRole("button", { name: "Fjern" }).click();
    await expect(panel).not.toContainText("Smil Klinikken");
    expect((await (await api(page, "GET", "/health-contacts")).json()).items).toHaveLength(0);
  },
});
