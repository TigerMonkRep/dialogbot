import { expect, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { DEMO_PASSWORD, latestMailLink, uniqueEmail } from "../../helpers";

/* Shared helpers for QA wave 2 (P1), instance E2B: onboarding (O01–O07), setup guide (G01–G08) and the in-app assistant (X19).
 * Only fake adapters; every e-mail/name is unique per run. */
export const CSRF = { "x-requested-with": "dialogbot" };
export const BASE = process.env.BASE_URL ?? "http://localhost:3000";

export function evid(id: string, info: TestInfo, name: string) {
  const dir = `${__dirname}/../../../../qa/evidence/${id}`;
  mkdirSync(dir, { recursive: true });
  return `${dir}/${info.project.name}-${name}.png`;
}

export async function snap(page: Page, id: string, info: TestInfo, name: string) {
  await page.screenshot({ path: evid(id, info, name), fullPage: true });
}

export const api = (page: Page) => ({
  get: async (path: string) => {
    const r = await page.request.get(`/api/backend${path}`);
    return { status: r.status(), body: await r.json().catch(() => null) };
  },
  send: async (method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, data: unknown = {}) => {
    const r = await page.request.fetch(`/api/backend${path}`, { method, headers: CSRF, data });
    return { status: r.status(), body: await r.json().catch(() => null) };
  },
});

/** Registers + verifies a user in a fresh context (no workspace). */
export async function freshUser(browser: Browser, info: TestInfo, tag: string, intent = "reception"): Promise<{ ctx: BrowserContext; page: Page; email: string }> {
  const ctx = await browser.newContext({ baseURL: BASE, viewport: info.project.use.viewport ?? undefined, locale: "da-DK", timezoneId: "Europe/Copenhagen" });
  const page = await ctx.newPage();
  const email = uniqueEmail(tag, info);
  const r = await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: `QA ${tag}`, signup_intent: intent } });
  expect(r.status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  const token = (await latestMailLink(page.request, /token=[\w-]+/)).split("=")[1];
  expect((await page.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  return { ctx, page, email };
}

/** A colleague with `role` in the owner's workspace, logged in in its own context, current workspace set. */
export async function colleague(owner: Page, browser: Browser, info: TestInfo, wsId: string, role: "admin" | "staff" | "reader", skipGate = true) {
  const u = await freshUser(browser, info, `e2b-${role}`);
  const inv = await owner.request.post(`/api/backend/workspaces/${wsId}/invitations`, { headers: CSRF, data: { email: u.email, role } });
  expect(inv.status(), await inv.text()).toBeLessThan(300);
  const link = await latestMailLink(u.page.request, /http\S+\/invite\/[\w-]+/);
  const token = link.split("/invite/")[1];
  const acc = await u.page.request.post("/api/backend/invitations/accept", { headers: CSRF, data: { token } });
  expect(acc.ok(), await acc.text()).toBeTruthy();
  await u.page.request.post("/api/auth/workspace", { headers: CSRF, data: { workspace_id: wsId } });
  if (skipGate) await u.ctx.addCookies([{ name: "db_setup_later", value: "1", url: BASE }]);
  return u;
}

/** Fill trin 1 so it is «done» (name, phone, description) via the API. */
export async function completeProfile(page: Page, wsId: string, over: Record<string, unknown> = {}) {
  const a = api(page);
  const cur = (await a.get(`/workspaces/${wsId}/profile`)).body;
  const r = await a.send("PUT", `/workspaces/${wsId}/profile`, { ...cur, expected_version: cur.version, legal_name: cur.legal_name || "Fjord Gulv QA", description: "Gulvafslibning og lakering i Aarhus", phone: "+4586000000", ...over });
  expect(r.status, JSON.stringify(r.body)).toBe(200);
  return r.body;
}

export async function setGoals(page: Page, wsId: string, patch: Record<string, unknown>) {
  const a = api(page);
  const cur = (await a.get(`/workspaces/${wsId}/goals`)).body;
  const r = await a.send("PUT", `/workspaces/${wsId}/goals`, { ...cur, ...patch, expected_version: cur.version });
  expect(r.status, JSON.stringify(r.body)).toBe(200);
  return r.body;
}

/** No horizontal scrolling (mobile 390). */
export async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
}

/** Logged-in UI must never say «Staging». */
export async function noStaging(page: Page) {
  await expect(page.locator("body")).not.toContainText(/staging/i);
}

/** The stack's PUBLIC_BASE_URL points at the default API port; send the simulated OAuth callback to the running API instead. */
export async function routeOAuthToApi(page: Page) {
  const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
  await page.route(/\/api\/v1\/integrations\/oauth\/.*\/callback/, async (route) => {
    const u = new URL(route.request().url());
    if (u.origin === apiBase) return route.continue();
    const res = await route.fetch({ url: `${apiBase}${u.pathname}${u.search}`, maxRedirects: 0 });
    await route.fulfill({ response: res });
  });
}
