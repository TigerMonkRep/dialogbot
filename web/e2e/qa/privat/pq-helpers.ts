import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { DEMO_PASSWORD, latestMailLink, skipSetupGate } from "../../helpers";

/** e2e-privat (PQ) helpers. These specs need a REAL Privat backend: the shared stack (:8000) runs without
 *  PRIVAT_ENABLED and every /privat call answers 403 privat_not_enabled. Start tests/qa/qa_privat_stack.py (API :8100,
 *  own DB, fake Stripe + fake Vapi, no network) and a second `next start -p 3100` with API_BASE_URL=http://localhost:8100,
 *  then run with BASE_URL=http://localhost:3100 QA_PRIV_API=http://localhost:8100. */
export const QA_API = process.env.QA_PRIV_API ?? "http://localhost:8100";
export const CSRF = { "x-requested-with": "dialogbot" };

export async function needsPrivatStack(request: APIRequestContext) {
  const r = await request.get(`${QA_API}/__qa/calls`).catch(() => null);
  return !!r && r.ok();
}

export const pqEmail = (tag: string, info: TestInfo) => `qa-pq-${tag}-${info.project.name}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

/** Register + log in (httpOnly cookie in this page's context) + verify e-mail. No private account yet (the app creates
 *  it on first load, like a real sign-up). */
export async function privatUser(page: Page, info: TestInfo, tag: string, name = "Mette Hansen") {
  const email = pqEmail(tag, info);
  const r = await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: name } });
  expect(r.status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  const token = (await latestMailLink(page.request, /token=[\w-]+/)).split("=")[1];
  expect((await page.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  await skipSetupGate(page);
  const acc = await page.request.post("/api/backend/privat/account", { headers: CSRF });
  expect(acc.ok(), await acc.text()).toBeTruthy();
  return { email };
}

export async function subscription(page: Page) {
  const r = await page.request.get("/api/backend/privat/subscription");
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as { status: string; plan: string; entitled: boolean; trial_days_left: number; calls_quota: number };
}

export async function stripeState(request: APIRequestContext) {
  return (await (await request.get(`${QA_API}/__qa/stripe/sessions`)).json()) as {
    sessions: { id: string; status: string; customer_email: string; subscription: string | null; metadata: Record<string, string>;
      payload: Record<string, unknown>; attempts: Record<string, string>[] }[];
  };
}

export async function dialled(request: APIRequestContext) {
  return ((await (await request.get(`${QA_API}/__qa/calls`)).json()) as { dialled: { payload: { metadata: Record<string, string> } }[] }).dialled;
}

export async function waitIdle(page: Page) {
  await expect(page.locator("[data-busy]").first()).toHaveAttribute("data-busy", "false", { timeout: 20_000 });
}

export async function evidence(page: Page, info: TestInfo, scenario: string, name: string) {
  const path = `../qa/evidence/${scenario}/${info.project.name}-${name}.png`;
  await page.screenshot({ path, fullPage: true });
  await info.attach(name, { path, contentType: "image/png" });
}

/** The 14-day trial through the (fake) Stripe Checkout, without the browser: checkout → submit the hosted form with
 *  the success card → the session's success_url. Same backend path as a real return (?session_id= sync). */
export async function startTrial(page: Page) {
  const { url } = await (await page.request.post("/api/backend/privat/subscription/checkout", { headers: CSRF, data: { plan: "plus", interval: "month" } })).json();
  const sid = String(url).split("/pay/")[1];
  const r = await page.request.post(url, { form: { name: "Mette Hansen", line1: "Abildgade 18", postal_code: "8200", city: "Aarhus N",
    phone: "+4520304050", email: "x@example.com", card: "4242424242424242" }, maxRedirects: 0 });
  expect(r.status()).toBe(303);
  const s = await (await page.request.get(`/api/backend/privat/subscription?session_id=${sid}`)).json();
  expect([s.status, s.entitled]).toEqual(["trial", true]);
}

/** Send a chat message through the API; returns the id of the task it made (if any). */
export async function say(page: Page, text: string): Promise<string | undefined> {
  const r = await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const body = (await r.json()) as { messages: { kind: string; task_id: string | null; role: string }[] };
  return body.messages.find((m) => m.kind === "task" && m.task_id)?.task_id ?? undefined;
}
