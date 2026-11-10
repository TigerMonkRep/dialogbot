import { expect, test } from "@playwright/test";
import { closeAll, EVID, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W05 – callback scheduling: «Available windows, local time-zone explanation, no slots and alternate follow-up.» */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W05 · tidsrummene i widgetten er de samme som API'ets, og «Ingen præference»/«Hurtigst muligt» findes altid", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const api = await (await page.request.get(`http://localhost:8200/api/v1/public/webchat/${w.key}/callback-windows`)).json();
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const sel = chat.locator("form.contact").getByLabel("Hvornår må vi ringe?");
  await expect(sel.locator("option")).toHaveCount(api.options.length + 1);
  expect(await sel.locator("option").allTextContents()).toEqual(["Ingen præference", ...api.options.map((o: { label: string }) => o.label)]);
  expect(api.options[0]).toEqual({ key: "asap", label: "Hurtigst muligt" });
  await v.screenshot({ path: `${EVID("W05")}/${info.project.name}-tidsrum.png` });
  await close();
});

test("W05 · tidszonen forklares for den besøgende (tidsrummene er i virksomhedens lokale tid)", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  // Requirement W05: «local time-zone explanation». callback-windows returns `timezone`, frame.js never shows it.
  await expect(chat.locator("form.contact")).toContainText(/dansk tid|Europe\/Copenhagen|tidszone|lokal tid/i);
  await close();
});

test("W05 · tidsrummene følger virksomhedens åbningstider: lukket på hverdage = ingen hverdags-tidsrum", async ({ page, browser }, info) => {
  // Fjord Gulv variant only open in weekends. Today (run date) is a weekday evening: the next weekday is closed.
  w = await widgetWorkspace(page, info, { hours: [{ days: ["sat", "sun"], open: "09:00", close: "13:00" }] });
  const api = await (await page.request.get(`http://localhost:8200/api/v1/public/webchat/${w.key}/callback-windows`)).json();
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  await v.screenshot({ path: `${EVID("W05")}/${info.project.name}-lukket-hverdage.png` });
  const today = new Date().toLocaleDateString("en-GB", { weekday: "short", timeZone: "Europe/Copenhagen" });
  test.skip(today === "Fri" || today === "Sat" || today === "Sun", "the assertion is about weekday windows");
  // callback.options() offers fixed Mon–Fri 08–16 windows regardless of approved opening hours (app/modules/leads/callback.py:22)
  expect(api.options.map((o: { label: string }) => o.label).filter((l: string) => /formiddag|eftermiddag/.test(l))).toEqual([]);
  await close();
});
