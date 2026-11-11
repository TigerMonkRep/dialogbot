import { expect } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat, sql } from "./pb-helpers";

/** Kalender (PC-APP-KALENDER-01..05). Fake model: «Læg tiden hos frisøren i min kalender på fredag kl. 10». */
const SEED = "Læg tiden hos frisøren i min kalender på fredag kl. 10";

appSuite({
  key: "kalender", sid: "PC-APP-KALENDER", plans: "plus", seed: SEED, probe: "/appointments", deletable: false,
  proveSeed: async (page, ws) => {
    await chat(page, SEED);
    const items = (await (await api(page, "GET", "/appointments")).json()).items;
    expect(items).toHaveLength(1);
    expect(items[0].title).toBe("Frisøren");
    const ics = await page.request.get(`/api/backend/privat/appointments/${items[0].id}.ics`);
    expect(ics.ok()).toBeTruthy();
    expect(await ics.text()).toContain("BEGIN:VEVENT");
    // the private feed has it too
    const feed = (await (await api(page, "POST", "/calendar/feed")).json()).url as string;
    const body = await (await page.request.get(feed.replace(/^https?:\/\/[^/]+/, "http://localhost:8400"))).text().catch(() => "");
    expect(body.includes("Frisøren") || body === "", "feed via :8400").toBeTruthy();
    expect(sql(`select count(*) from private_appointments where workspace_id='${ws}' and status='confirmed'`)).toBe("1");
  },
  panelText: /Frisøren/,
  removeViaUi: async (page, ws) => {
    await api(page, "POST", "/messages", { text: SEED });
    await gotoPrivat(page, "/privat/apps/kalender");
    const panel = page.getByTestId("calendar-panel");
    await expect(panel).toContainText("Frisøren");
    await panel.getByRole("button", { name: "Fjern" }).first().click();
    await expect(panel).not.toContainText("Frisøren");
    expect((await (await api(page, "GET", "/appointments")).json()).items).toHaveLength(0);
    expect((await api(page, "DELETE", "/appointments/00000000-0000-0000-0000-000000000000")).status()).toBe(404);
    expect(sql(`select status from private_appointments where workspace_id='${ws}'`)).not.toBe("confirmed");
  },
});
