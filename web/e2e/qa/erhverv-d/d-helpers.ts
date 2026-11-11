import { expect, type APIRequestContext, type Browser, type FrameLocator, type Page, type TestInfo } from "@playwright/test";
import { freshOwner, serve } from "../../helpers";

/* Shared setup for QA wave 2 instance D (E2D). The customer's website is a fake site on its own port (4318), so it
 * never clashes with :4000 (helpers.CUSTOMER_SITE) or :4127 (erhverv-b). Only canonical demo data (Fjord Gulv). */
export const CSRF = { "x-requested-with": "dialogbot" };
// One port per Playwright worker (verifier, bølge 2): with --workers=2 two W-specs listened on :4318 at once →
// EADDRINUSE. TEST_PARALLEL_INDEX is 0 with --workers=1, so single-worker runs keep :4318.
export const SITE_PORT = 4318 + 100 * Number(process.env.TEST_PARALLEL_INDEX ?? 0);
export const SITE = `http://localhost:${SITE_PORT}`;
export const EVID = (id: string) => `../qa/evidence/${id}`;

export async function approve(req: APIRequestContext, wsId: string, kind: string, title: string, content: Record<string, unknown>) {
  const item = await (await req.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind, title, content } })).json();
  await req.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  const r = await req.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF });
  expect(r.ok(), await r.text()).toBeTruthy();
  return item;
}

export const ALL_WEEK = [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], open: "08:00", close: "20:00" }];

export type Widget = { wsId: string; key: string; embed: string; servers: import("node:http").Server[] };

/** Fresh owner + approved knowledge + webchat on SITE; optional online booking with one type. */
export async function widgetWorkspace(page: Page, info: TestInfo, opts: { booking?: boolean; greeting?: string; hours?: unknown } = {}): Promise<Widget> {
  const { wsId } = await freshOwner(page, info);
  await approve(page.request, wsId, "opening_hours", "Åbningstider", { weekly: opts.hours ?? ALL_WEEK });
  await approve(page.request, wsId, "service", "Gulvafslibning", {});
  if (opts.booking) {
    await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } });
    const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/settings`)).json();
    const r = await page.request.put(`/api/backend/workspaces/${wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 } });
    expect(r.ok(), await r.text()).toBeTruthy();
  }
  const wc = await (await page.request.get(`/api/backend/workspaces/${wsId}/webchat`)).json();
  const put = await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: wc.version, enabled: true, allowed_origins: [SITE], greeting: opts.greeting ?? "" } });
  expect(put.ok(), await put.text()).toBeTruthy();
  const w = await put.json();
  const servers = [await serve(SITE_PORT, `<!doctype html><html lang="da"><head><title>Fjord Gulv</title></head><body><h1>Fjord Gulv ApS</h1>${w.embed_code}</body></html>`)];
  return { wsId, key: w.widget_key, embed: w.embed_code, servers };
}

export async function closeAll(servers: import("node:http").Server[]) {
  while (servers.length) await new Promise((r) => servers.pop()!.close(r));
}

/** The p1 stack's API runs on :8200 without PUBLIC_BASE_URL, so the embed code and the frame's own origin say
 *  :8000 (config default). A visitor context forwards :8000 → :8200 unchanged (Origin header kept), which keeps the
 *  frame-origin checks real. Environment workaround only – not a product finding. */
export async function newVisitorContext(browser: Browser, page: Page) {
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined, locale: "da-DK", timezoneId: "Europe/Copenhagen" });
  await ctx.route("http://localhost:8000/**", async (route) => {
    try {
      const res = await route.fetch({ url: route.request().url().replace("localhost:8000", "localhost:8200") });
      await route.fulfill({ response: res });
    } catch { /* context closed while a poll was in flight */ }
  });
  return ctx;
}

/** A visitor on the customer's site (own context, no Dialogbot cookies) with the chat opened. */
export async function visitor(browser: Browser, page: Page): Promise<{ v: Page; chat: FrameLocator; close: () => Promise<void> }> {
  const ctx = await newVisitorContext(browser, page);
  const v = await ctx.newPage();
  await v.goto(`${SITE}/`);
  await v.getByRole("button", { name: "Åbn chat" }).click();
  const chat = v.frameLocator('iframe[title^="Chat med"]');
  await expect(chat.locator("textarea")).toBeVisible();
  return { v, chat, close: () => ctx.close() };
}
