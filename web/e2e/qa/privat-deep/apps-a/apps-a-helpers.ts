import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { expect, test, type Page, type Response, type TestInfo } from "@playwright/test";
import { CSRF, needsPrivatStack, privatUser, waitIdle } from "../../privat/pq-helpers";

/** Privat dybderunde fase 2 – apps A (prefix PA, owner e2e-privat). The REAL stack: web :3400 → API :8400
 *  (tests/qa/qa_privat_stack.py, db qa_privdeep_stack, fake Stripe/Vapi, AI_PROVIDER=fake, no network).
 *    cd web && BASE_URL=http://localhost:3400 QA_PRIV_API=http://localhost:8400 \
 *      npx playwright test e2e/qa/privat-deep/apps-a --workers=1 --output=/home/claude/pd-results/PA
 *  Every test proves it hit :8400 and not the in-browser simulation (fake.ts): the browser's /api/backend/privat/* calls
 *  answer 2xx/4xx from the API (never privat_not_enabled), and what the UI made is read back DIRECTLY from :8400 and
 *  from the database. The chat model is the fake (app/modules/privat/fake.py): phrasings below use ISO dates. */

export const API = process.env.QA_PRIV_API ?? "http://localhost:8400";
export const DB_URL = process.env.QA_PRIV_DB_URL ?? "postgresql://postgres:postgres@localhost:5432/qa_privdeep_stack";

export type Addon = {
  key: string; name: string; enabled: boolean; status: string; requires_plan: boolean; what: string; example: string;
  steps: string[]; needs: string[]; permissions: string[]; tagline: string; included: boolean; included_in: string[];
  setup: { done: number; total: number }; disabled_at: string | null; data_deletable: boolean; summary_line: string | null;
  price_text: string; enabled_at: string | null;
};

export function guard() {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await needsPrivatStack(request)), `kræver qa_privat_stack på ${API} og next på BASE_URL med API_BASE_URL=${API}`);
  });
}

/** Read-only SQL (and the two persona shortcuts below) against the stack's own database. */
export function sql(q: string): string[] {
  return execFileSync("psql", [DB_URL, "-Atc", q], { encoding: "utf8" }).trim().split("\n").filter(Boolean);
}
const lit = (s: string) => `'${s.replace(/'/g, "''")}'`;
export const wsOf = (email: string) =>
  sql(`select p.workspace_id from private_profiles p join users u on u.id=p.user_id where u.email_normalized=${lit(email.toLowerCase())}`)[0];

/** Records every browser call to the Privat API; `assertReal()` fails if the web fell back to its simulation. */
export function backendTrace(page: Page) {
  const seen: { url: string; status: number }[] = [];
  const bad: string[] = [];
  page.on("response", async (r: Response) => {
    const u = r.url();
    if (!u.includes("/api/backend/privat/")) return;
    seen.push({ url: u, status: r.status() });
    if (r.status() === 404 || r.status() === 403) {
      const body = await r.text().catch(() => "");
      if (/privat_not_enabled|feature_disabled/.test(body)) bad.push(`${r.status()} ${u} ${body.slice(0, 80)}`);
    }
  });
  return {
    seen,
    assertReal() {
      expect(seen.length, "browseren har talt med Privat-API'et").toBeGreaterThan(0);
      expect(bad, "ingen fallback til simuleringen").toEqual([]);
    },
  };
}

/** GET straight from the API on :8400 (same session cookie – cookies are per host, not per port). */
export async function direct<T = unknown>(page: Page, path: string): Promise<{ status: number; body: T }> {
  const sess = (await page.context().cookies()).find((c) => c.name === "db_session");
  expect(sess, "session-cookie").toBeTruthy();
  const r = await page.request.get(`${API}/api/v1${path}`, { headers: { ...CSRF, authorization: `Bearer ${sess!.value}` } });
  return { status: r.status(), body: (await r.json().catch(() => ({}))) as T };
}
export async function catalog(page: Page): Promise<Record<string, Addon>> {
  const r = await direct<Addon[]>(page, "/privat/addons");
  expect(r.status).toBe(200);
  return Object.fromEntries(r.body.map((a) => [a.key, a]));
}

export type Persona = "none" | "trial" | "basis" | "expired";

/** A fresh account in the browser context. none = signed up, no checkout; trial = 14 days Plus through the fake
 *  Stripe Checkout (card 4242); basis = Basis through the same checkout; expired = trial whose end is in the past. */
export async function persona(page: Page, info: TestInfo, tag: string, who: Persona = "trial", name = "Mette Hansen") {
  await page.setExtraHTTPHeaders({ "x-real-ip": `10.${(Date.now() >> 8) % 250}.${Math.floor(Math.random() * 250)}.${1 + Math.floor(Math.random() * 250)}` });
  const { email } = await privatUser(page, info, `pa-${tag}`, name);
  if (who !== "none") await checkout(page, who === "basis" ? "basis" : "plus");
  if (who === "expired") {
    sql(`update private_subscriptions set trial_ends_at=now()-interval '1 day' where workspace_id=${lit(wsOf(email))}`);
  }
  return { email, ws: wsOf(email) };
}

async function checkout(page: Page, plan: "plus" | "basis") {
  const c = await page.request.post("/api/backend/privat/subscription/checkout", { headers: CSRF, data: { plan, interval: "month" } });
  expect(c.ok(), await c.text()).toBeTruthy();
  const { url } = await c.json();
  const sid = String(url).split("/pay/")[1];
  const r = await page.request.post(url, { form: { name: "Mette Hansen", line1: "Abildgade 18", postal_code: "8200", city: "Aarhus N",
    phone: "+4520304050", email: "x@example.com", card: "4242424242424242" }, maxRedirects: 0 });
  expect(r.status()).toBe(303);
  const s = await (await page.request.get(`/api/backend/privat/subscription?session_id=${sid}`)).json();
  expect(s.status).toBe("trial");
  expect(s.plan).toBe(plan);
}

export async function enableApi(page: Page, key: string) {
  const r = await page.request.post(`/api/backend/privat/addons/${key}/enable`, { headers: CSRF });
  expect(r.status(), await r.text()).toBe(200);
}

export async function shot(page: Page, info: TestInfo, scenario: string, name: string) {
  mkdirSync(`../qa/evidence/${scenario}`, { recursive: true });
  const path = `../qa/evidence/${scenario}/PA-${info.project.name}-${name}.png`;
  await page.screenshot({ path, fullPage: true });
  await info.attach(name, { path, contentType: "image/png" });
}

export async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "ingen vandret scroll").toBeLessThanOrEqual(1);
}

/** Type in the chat composer (Samtale) and wait for the answer. */
export async function sayInChat(page: Page, text: string) {
  await page.goto("/privat/samtale");
  await waitIdle(page);
  const input = page.locator("#privat-ask:visible").first();
  await input.fill(text);
  await input.press("Enter");
  await waitIdle(page);
  await expect(page.getByRole("region", { name: "Samtale" }).getByText(text.slice(0, 30)).last()).toBeVisible();
}

export const strip = (s: string) => s.replace(/^«|»$/g, "");
export { waitIdle, CSRF };
