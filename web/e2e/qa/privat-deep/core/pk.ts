import { mkdirSync } from "node:fs";
import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { skipSetupGate } from "../../../helpers";

/** PK (e2e-privat, Privat-dybderunde fase 2, kerneflows). Kører mod den rigtige Privat-stak:
 *    API http://localhost:8400 (tests/qa/qa_privat_stack.py, falsk Stripe/Vapi, intet netværk) og web :3400.
 *    cd web && BASE_URL=http://localhost:3400 QA_PRIV_API=http://localhost:8400 \
 *      npx playwright test e2e/qa/privat-deep/core --workers=1 --output=/home/claude/pd-results/PK
 *  Hvert API-kald fra siden går via /api/backend → :8400; `assertRealBackend` sikrer, at vi IKKE tester web-fake'en. */
export const API = process.env.QA_PRIV_API ?? "http://localhost:8400";
export const CSRF = { "x-requested-with": "dialogbot" };
export const PW = "Korrekt-Hest-Batteri-42";
export const uniqueIp = () => `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${1 + Math.floor(Math.random() * 250)}`;

export async function stackUp(request: APIRequestContext) {
  const r = await request.get(`${API}/__qa/calls`).catch(() => null);
  return !!r && r.ok();
}

export async function shot(page: Page, info: TestInfo, scenario: string, name: string) {
  const dir = `../qa/evidence/${scenario}`;
  mkdirSync(dir, { recursive: true });
  const path = `${dir}/PK-${info.project.name}-${name}.png`;
  await page.screenshot({ path, fullPage: true });
  await info.attach(name, { path, contentType: "image/png" });
}

/** Register + log in (cookie in this page's context) + verify e-mail + create the private account. */
export async function user(page: Page, info: TestInfo, tag: string, name = "Mette Hansen", account = true) {
  const email = `qa-pk-${tag}-${info.project.name}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.context().setExtraHTTPHeaders({ "x-real-ip": uniqueIp() });
  const r = await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: PW, display_name: name } });
  expect(r.status(), await r.text()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: PW } })).ok()).toBeTruthy();
  let token = "";
  for (let i = 0; i < 40 && !token; i++) {
    const box = (await (await page.request.get("/api/backend/dev/mailbox")).json()) as { items: { body_text: string }[] };
    token = box.items.map((m) => /token=([\w-]+)/.exec(m.body_text)?.[1]).find(Boolean) ?? "";
    if (!token) await page.waitForTimeout(250);
  }
  expect((await page.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  await skipSetupGate(page);
  if (account) expect((await page.request.post("/api/backend/privat/account", { headers: CSRF })).ok()).toBeTruthy();
  return { email };
}

/** 14-day trial through the fake Stripe Checkout without the browser UI. */
export async function trial(page: Page, plan = "plus") {
  const { url } = await (await page.request.post("/api/backend/privat/subscription/checkout", { headers: CSRF, data: { plan, interval: "month" } })).json();
  const sid = String(url).split("/pay/")[1];
  const r = await page.request.post(url, { form: { name: "Mette Hansen", line1: "Abildgade 18", postal_code: "8200", city: "Aarhus N", phone: "+4520304050", email: "x@example.com", card: "4242424242424242" }, maxRedirects: 0 });
  expect(r.status()).toBe(303);
  const s = await (await page.request.get(`/api/backend/privat/subscription?session_id=${sid}`)).json();
  expect(s.entitled).toBe(true);
}

export async function say(page: Page, text: string): Promise<string | undefined> {
  const r = await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text } });
  expect(r.ok(), await r.text()).toBeTruthy();
  return ((await r.json()) as { messages: { task_id: string | null }[] }).messages.find((m) => m.task_id)?.task_id ?? undefined;
}

/** Fails when the page shows the in-browser simulation instead of talking to :8400. */
export async function assertRealBackend(page: Page) {
  await expect(page.getByText(/Simuleret|Demo-tilstand|eksempeldata/i).first()).toHaveCount(0);
}

export async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "ingen vandret scroll").toBeLessThanOrEqual(0);
}
