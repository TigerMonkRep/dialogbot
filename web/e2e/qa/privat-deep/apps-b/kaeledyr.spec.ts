import { expect } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat, sql } from "./pb-helpers";

/** Kæledyr (PC-APP-KAELEDYR-01..05). The fake model only reads ISO dates («2027-03-01»); the store's «1. marts» is a
 *  fake-model limit, not the product. -04 includes F-PB-01 (Mis/Misser). */
const SEED = "Vores hund Bella skal vaccineres 2027-03-01 og have ormekur hver 3. måned";

appSuite({
  key: "kaeledyr", sid: "PC-APP-KAELEDYR", plans: "plus", seed: SEED, probe: "/apps/kaeledyr/overview", deletable: true,
  proveSeed: async (page, ws) => {
    await chat(page, SEED);
    const p = JSON.parse(sql(`select data::text from private_app_data where workspace_id='${ws}' and app_key='kaeledyr'`)).items[0];
    expect(p).toMatchObject({ name: "Bella", kind: "hund", vaccination_due: "2027-03-01" });
    expect(p.worming.every).toBe(3);
    await chat(page, "Book dyrlæge til Bella");  // no vet saved: no call
    expect(sql(`select count(*) from private_calls where workspace_id='${ws}'`)).toBe("0");
  },
  panelText: /Bella/,
  removeViaUi: async (page, ws) => {
    await api(page, "POST", "/messages", { text: "Vores kat Misser skal vaccineres 2027-03-01" });
    await api(page, "POST", "/messages", { text: "Vores kat Mis skal vaccineres 2027-06-15" });
    const names = JSON.parse(sql(`select data::text from private_app_data where workspace_id='${ws}' and app_key='kaeledyr'`)).items.map((x: { name: string }) => x.name).sort();
    expect.soft(names, "F-PB-01: Mis må ikke overskrive Misser").toEqual(["Mis", "Misser"]);
    await gotoPrivat(page, "/privat/apps/kaeledyr");
    const panel = page.getByTestId("household-panel");
    await expect(panel).toContainText("Misser");
    await panel.getByRole("button", { name: "Fjern" }).first().click();
    await expect.poll(async () => (await (await api(page, "GET", "/apps/kaeledyr/overview")).json()).items.length).toBe(names.length - 1);
    expect((await api(page, "DELETE", "/apps/kaeledyr/items/findes-ikke")).status()).toBe(404);
  },
});
