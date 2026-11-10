import { expect } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat, gotoPrivat } from "./pb-helpers";

/** Madplan (PC-APP-MADPLAN-01..05). The fake model needs two turns: preferences, then «ja, gem madplanen»
 *  (save_meal_plan refuses until the user said yes – the real model writes the proposal in between). */
const SEED = "Vi er 4, og børnene spiser ikke fisk";

appSuite({
  key: "madplan", sid: "PC-APP-MADPLAN", plans: "plus", seed: SEED, probe: "/meals/preferences", deletable: true,
  proveSeed: async (page) => {
    await chat(page, SEED);
    const p = await (await api(page, "GET", "/meals/preferences")).json();
    expect(p.people).toBe(4);
    expect(p.avoid).toContain("fisk");
    const out = await chat(page, "Ja, gem madplanen");
    const tasks = out.messages.filter((m) => m.kind === "task");
    expect(tasks).toHaveLength(2);
    const shop = await (await api(page, "GET", `/tasks/${tasks[1].task_id}`)).json();
    const texts = shop.items.map((i: { text: string }) => i.text).join(" | ").toLowerCase();
    expect(texts).not.toMatch(/fisk|laks|torsk/);
    await expect(page.getByText(/Madplanen er gemt med 2 retter til 4 personer/)).toBeVisible();
  },
  panelText: null,
  removeViaUi: async (page) => {
    await gotoPrivat(page, "/privat/apps/madplan");
    const panel = page.getByTestId("meals-panel");
    await panel.getByLabel("Hvor mange er I?").fill("3");
    await panel.getByLabel("Hvad spiser I ikke (allergier)?").fill("nødder 🥜 " + "x".repeat(480));
    await panel.getByRole("button", { name: "Gem" }).click();
    await expect.poll(async () => (await (await api(page, "GET", "/meals/preferences")).json()).people).toBe(3);
    expect((await (await api(page, "GET", "/meals/preferences")).json()).avoid).toContain("🥜");
    expect((await api(page, "PUT", "/meals/preferences", { people: 21 })).status()).toBe(422);
  },
});
