import { expect, test } from "@playwright/test";
import { closeAll, CSRF, EVID, newVisitorContext, SITE, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W01 – widget launcher/home: «Collapsed launcher and open client-branded chat/callback choices; “Book en tid” when
 * configured and supported.» The widget runs on a foreign origin (SITE, :4318). */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W01 · lukket launcher, åbnet hjem med «Bliv kontaktet» og «Book en tid» når booking er slået til; luk igen", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info, { booking: true });
  const ctx = await newVisitorContext(browser, page);
  const v = await ctx.newPage();
  await v.goto(`${SITE}/`);
  const launcher = v.getByRole("button", { name: "Åbn chat" });
  await expect(launcher).toHaveAttribute("aria-expanded", "false");
  // collapsed: the iframe is not loaded before the visitor asks for it (no chat traffic for passive visitors)
  expect(await v.evaluate(() => (document.querySelector("[data-dialogbot]")?.shadowRoot?.querySelector("iframe") as HTMLIFrameElement | null)?.getAttribute("src") ?? null)).toBeNull();
  await v.screenshot({ path: `${EVID("W01")}/${info.project.name}-lukket.png` });
  await launcher.click();
  await expect(v.getByRole("button", { name: "Luk chat" }).first()).toHaveAttribute("aria-expanded", "true");
  const chat = v.frameLocator('iframe[title^="Chat med"]');
  await expect(chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" })).toBeVisible();
  await expect(chat.getByRole("button", { name: "Book en tid" })).toBeVisible();
  await expect(chat.locator("textarea")).toBeEditable();
  await v.screenshot({ path: `${EVID("W01")}/${info.project.name}-aaben.png` });
  // the × in the frame closes the panel again (postMessage to the loader)
  await chat.getByRole("button", { name: "Luk chat" }).click();
  await expect(v.getByRole("button", { name: "Åbn chat" })).toHaveAttribute("aria-expanded", "false");
  await ctx.close();
});

test("W01 · uden online booking: ingen «Book en tid»; booking slået til uden aktive typer: heller ingen", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info, { booking: false });
  let vis = await visitor(browser, page);
  await expect(vis.chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" })).toBeVisible();
  await expect(vis.chat.getByRole("button", { name: "Book en tid" })).toBeHidden();
  await vis.close();
  // switched on, but no active booking type -> still not offered (nothing to book)
  const s = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings/settings`)).json();
  await page.request.put(`/api/backend/workspaces/${w.wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 } });
  vis = await visitor(browser, page);
  await expect(vis.chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" })).toBeVisible();
  await expect(vis.chat.getByRole("button", { name: "Book en tid" })).toBeHidden();
  await vis.close();
});

test("W01 · ikke-tilladt site og slukket widget viser ingen launcher", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { serve } = await import("../../helpers");
  w.servers.push(await serve(4319, `<!doctype html><html><body><h1>Fremmed side</h1>${w.embed}</body></html>`));
  const ctx = await newVisitorContext(browser, page);
  const v = await ctx.newPage();
  await v.goto("http://localhost:4319/");
  await v.waitForTimeout(1500);
  await expect(v.getByRole("button", { name: "Åbn chat" })).toHaveCount(0);
  const wc = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/webchat`)).json();
  await page.request.put(`/api/backend/workspaces/${w.wsId}/webchat`, { headers: CSRF, data: { expected_version: wc.version, enabled: false, allowed_origins: [SITE], greeting: "" } });
  await v.goto(`${SITE}/`);
  await v.waitForTimeout(1500);
  await expect(v.getByRole("button", { name: "Åbn chat" })).toHaveCount(0);
  await ctx.close();
});

test("W01 · widgetten er kundens (client-branded): virksomhedens navn står i chatvinduet, ikke kun «Digital assistent»", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const ws = await (await page.request.get(`/api/backend/workspaces/${w.wsId}`)).json();
  const vis = await visitor(browser, page);
  await vis.v.screenshot({ path: `${EVID("W01")}/${info.project.name}-branding.png` });
  // Requirement W01: «open client-branded chat». The greeting may mention the name, but the frame header/title must.
  await expect(vis.chat.locator("header")).toContainText(ws.name);
  await vis.close();
});
