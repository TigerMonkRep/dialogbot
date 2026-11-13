import { expect, type APIRequestContext, type Browser, type BrowserContext, type FrameLocator, type Page, type TestInfo } from "@playwright/test";
import { freshOwner, serve } from "../../helpers";
import { smsCodeFor, uniqueIp, uniqueMobile } from "../erhverv-p1a/p1a-helpers";

/* Shared setup for QA wave 2 instance D (E2D). The customer's website is a fake site on its own port (4318), so it
 * never clashes with :4000 (helpers.CUSTOMER_SITE) or :4127 (erhverv-b). Only canonical demo data (Fjord Gulv). */
export const CSRF = { "x-requested-with": "dialogbot" };
// One port per Playwright worker (verifier, bølge 2): with --workers=2 two W-specs listened on :4318 at once →
// EADDRINUSE. TEST_PARALLEL_INDEX is 0 with --workers=1, so single-worker runs keep :4318.
export const SITE_PORT = 4318 + 100 * Number(process.env.TEST_PARALLEL_INDEX ?? 0);
export const SITE = `http://localhost:${SITE_PORT}`;
export const EVID = (id: string) => `../qa/evidence/${id}`;
/** The API the stack serves: API_BASE_URL (CI and the journeys stack: :8000; the local QA stack sets :8200). */
export const API = (process.env.API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
/** Without PUBLIC_BASE_URL the API's config default (:8000) is what the embed code, the chat frame and OAuth callbacks
 *  point at. */
const PUBLIC_DEFAULT = "http://localhost:8000";

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
  // the chat answers visitors only with a paid subscription (Fürster 12/11); no Stripe in E2E: confirmed = paid
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } })).ok()).toBeTruthy();
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

/** Environment workaround, not a product finding: when the API does not run on :8000 (the local QA stack: :8200 without
 *  PUBLIC_BASE_URL), requests to the :8000 default are forwarded unchanged (Origin header kept) to API_BASE_URL, which
 *  keeps the frame-origin checks real. On CI the API is on :8000 and nothing is rewritten.
 *  `maxRedirects: 0` for OAuth callbacks, whose redirect the browser must follow itself. */
export async function forwardPublicApi(ctx: BrowserContext, opts: { maxRedirects?: number } = {}) {
  if (new URL(API).port === "8000") return;
  await ctx.route(`${PUBLIC_DEFAULT}/**`, async (route) => {
    try {
      const res = await route.fetch({ url: route.request().url().replace(PUBLIC_DEFAULT, API), ...opts });
      await route.fulfill({ response: res });
    } catch { /* context closed while a poll was in flight */ }
  });
}

export async function newVisitorContext(browser: Browser, page: Page) {
  // Each visitor has their own address: the SMS-code door (W04) counts codes per client IP (5 an hour), and the E2E stack
  // takes the first X-Forwarded-For entry as the client (no CLIENT_IP_SECRET), so the catalogue's visitors don't share one.
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined, locale: "da-DK", timezoneId: "Europe/Copenhagen",
    extraHTTPHeaders: { "x-forwarded-for": uniqueIp() } });
  await forwardPublicApi(ctx);
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

/** A fresh Danish mobile per test (the per-number SMS budget is 4 an hour across every public door). */
export function uniquePhone(): { display: string; e164: string } {
  const m = uniqueMobile();
  return { display: `+45 ${m.replace(/(\d{2})(?=\d)/g, "$1 ")}`, e164: `+45${m}` };
}

/** W04 in the widget: after «Send» with a phone number, the code step asks for the SMS code (read from the API log, where
 *  the fake SMS adapter writes it) – type it and confirm. */
export async function confirmCode(chat: FrameLocator, e164: string) {
  const code = chat.locator(".code-step");
  await expect(code).toBeVisible();
  await code.getByLabel("Kode fra SMS").fill(await smsCodeFor(e164));
  await code.getByRole("button", { name: "Bekræft" }).click();
}
