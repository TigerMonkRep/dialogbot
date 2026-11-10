import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { expect, type Page, type Response, type TestInfo } from "@playwright/test";
import { CSRF, privatUser, startTrial } from "../../privat/pq-helpers";

/** PB (Privat dybderunde fase 2, apps B) helpers. Run against the REAL Privat stack:
 *    BASE_URL=http://localhost:3400 QA_PRIV_API=http://localhost:8400 npx playwright test e2e/qa/privat-deep/apps-b \
 *      --workers=1 --output=/home/claude/pd-results/PB
 *  Every test proves that what the browser saw came from :8400 (not the in-browser simulation, fake.ts): the
 *  x-request-id of a /api/backend/privat/* response must be in the :8400 API log (pd-api.log). Plan personas are put
 *  in place the way the Stripe webhook would leave them – one row in private_subscriptions of the stack's DB. */
export const API_LOG = process.env.QA_PRIV_LOG ?? "/home/claude/pd-api.log";
export const STACK_DB = process.env.QA_PRIV_DB_URL ?? "postgresql://postgres:postgres@localhost:5432/qa_privdeep_stack";
export const APP_KEYS = ["ring-for-mig", "oenskelister", "kalender", "pakker", "madplan", "regninger", "laege-og-tandlaege",
  "pakkeliste", "rejser", "kaeledyr"] as const;

export type Persona = "none" | "basis" | "expired" | "trial" | "familie";

export function sql(q: string): string {
  return execFileSync("psql", [STACK_DB, "-At", "-c", q], { encoding: "utf8" }).trim();
}

export async function wsOf(email: string): Promise<string> {
  return sql(`select p.workspace_id from private_profiles p join users u on u.id=p.user_id where u.email='${email.replace(/'/g, "")}'`);
}

/** A fresh Privat user (own x-real-ip) on the given plan persona. */
export async function pbUser(page: Page, info: TestInfo, tag: string, persona: Persona = "trial") {
  const ip = `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${1 + Math.floor(Math.random() * 250)}`;
  await page.context().setExtraHTTPHeaders({ "x-real-ip": ip });
  const { email } = await privatUser(page, info, `pb-${tag}`);
  const ws = await wsOf(email);
  if (persona === "trial" || persona === "expired") await startTrial(page);
  if (persona === "expired") sql(`update private_subscriptions set trial_ends_at=now()-interval '1 hour' where workspace_id='${ws}'`);
  if (persona === "basis" || persona === "familie") {
    const [plan, iv, days] = persona === "basis" ? ["basis", "month", 20] : ["familie", "year", 300];
    sql(`insert into private_subscriptions(workspace_id,plan,status,interval,current_period_end,stripe_customer_id,stripe_subscription_id)
         values ('${ws}','${plan}','active','${iv}',now()+interval '${days} days','cus_pb','sub_pb_${ws.slice(0, 8)}')
         on conflict (workspace_id) do update set plan='${plan}',status='active',interval='${iv}',current_period_end=now()+interval '${days} days',
         stripe_customer_id='cus_pb',stripe_subscription_id='sub_pb_${ws.slice(0, 8)}'`);
  }
  const sub = await (await page.request.get("/api/backend/privat/subscription")).json();
  const want = { none: "none", basis: "active", expired: "expired", trial: "trial", familie: "active" }[persona];
  expect([sub.status, persona === "basis" || persona === "familie" ? sub.plan : persona], `persona ${persona}`).toEqual([want, persona === "basis" || persona === "familie" ? persona : persona]);
  return { email, ws };
}

/** Asserts the response's x-request-id reached the :8400 API (its log). */
export async function cameFrom8400(r: Response | import("@playwright/test").APIResponse) {
  const id = r.headers()["x-request-id"];
  expect(id, "x-request-id fra API'et").toBeTruthy();
  await expect.poll(() => readFileSync(API_LOG, "utf8").includes(id!), { timeout: 10_000, message: `request ${id} i ${API_LOG}` }).toBe(true);
}

/** Opens a /privat page and proves the add-on list behind it came from :8400. */
export async function gotoPrivat(page: Page, path: string) {
  const wait = page.waitForResponse((r) => /\/api\/backend\/privat\/(addons|bootstrap)(\?|$)/.test(r.url()) && r.ok(), { timeout: 30_000 });
  await page.goto(path);
  await cameFrom8400(await wait);
}

export async function addon(page: Page, key: string) {
  const r = await page.request.get("/api/backend/privat/addons");
  expect(r.ok()).toBeTruthy();
  await cameFrom8400(r);
  return ((await r.json()) as Record<string, any>[]).find((a) => a.key === key)!;
}

export async function api(page: Page, method: "GET" | "POST" | "PUT" | "DELETE", path: string, data?: unknown) {
  const r = await page.request.fetch(`/api/backend/privat${path}`, { method, headers: CSRF, ...(data !== undefined ? { data } : {}) });
  await cameFrom8400(r);
  return r;
}

export function enabledRows(ws: string, key: string): number {
  return Number(sql(`select count(*) from private_addon_enabled where workspace_id='${ws}' and key='${key}'`));
}

export async function shot(page: Page, info: TestInfo, scenario: string, name: string) {
  const dir = `../qa/evidence/${scenario}`;
  mkdirSync(dir, { recursive: true });
  const path = `${dir}/PB-${info.project.name}-${name}.png`;
  await page.screenshot({ path }); // viewport only: fullPage crashes Chromium on this memory-starved box
  await info.attach(name, { path, contentType: "image/png" });
}

export async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "ingen vandret scroll").toBeLessThanOrEqual(0);
}

/** Type in the chat composer and send – the way a user does; waits until the API answered. */
export async function chat(page: Page, text: string) {
  await gotoPrivat(page, "/privat/samtale");
  const box = page.locator("#privat-ask");
  await expect(box).toBeVisible();
  await box.fill(text);
  const res = page.waitForResponse((r) => r.url().includes("/api/backend/privat/messages") && r.request().method() === "POST", { timeout: 30_000 });
  await box.press("Enter");
  const r = await res;
  expect(r.ok(), await r.text()).toBeTruthy();
  await cameFrom8400(r);
  return (await r.json()) as { messages: { role: string; kind: string; text: string | null; task_id: string | null }[] };
}

/** «Hvad den gør» on /privat/butik/<key> shows what the API says (what, example, steps, needs, permissions). */
export async function assertAbout(page: Page, a: Record<string, any>) {
  await expect(page.getByRole("heading", { level: 1, name: a.name })).toBeVisible();
  await expect(page.getByText(a.what, { exact: true })).toBeVisible();
  // The example sentence was cut from the shop page in the «mindre tekst» redesign (ui-ux-engineer, 2026-11-10);
  // the steps and the permissions (folded under «Den får lov til») are still the API's.
  for (const s of a.steps) await expect(page.getByText(s, { exact: true }).first()).toBeVisible();
  const perms = page.getByText("Den får lov til", { exact: true }).first();
  if (await perms.count()) await perms.click();
  for (const p of a.permissions) await expect(page.getByText(p, { exact: true }).first()).toBeVisible();
  for (const n of a.needs) await expect(page.getByText(n).first()).toBeVisible();
}

/** Butikken → the app's icon → «Hvad den gør». An app that is already on is not in Butikken any more (redesign
 *  2026-11-10) – its icon is under Mine apps; returns which page it landed on. */
export async function openFromShop(page: Page, key: string): Promise<"shop" | "app"> {
  const on = (await addon(page, key)).enabled;
  await gotoPrivat(page, on ? "/privat/apps" : "/privat/butik");
  await page.getByTestId(`app-row-${key}`).first().click();
  await expect(page).toHaveURL(new RegExp(`/privat/${on ? "apps" : "butik"}/${key}$`));
  return on ? "app" : "shop";
}

/** EnableSheet: «Slå X til» → consent → «slået til» with Trin 1 af N. Double-taps the confirm on purpose. */
export async function enableViaSheet(page: Page, a: Record<string, any>) {
  await page.getByTestId("enable-app").or(page.getByTestId("enable-again")).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (const p of a.permissions) await expect(dialog.getByText(p, { exact: true })).toBeVisible();
  const confirm = page.getByTestId("enable-confirm");
  await confirm.dblclick();
  await expect(dialog.getByText(new RegExp(`er slået til|slået til`, "i")).first()).toBeVisible({ timeout: 15_000 });
  if ((a.steps ?? []).length) await expect(dialog.getByText(new RegExp(`Trin 1 af ${a.steps.length}`))).toBeVisible();
}

/** App page → «Slå fra» → DisableSheet → confirm; lands on Mine apps with the Fortryd toast. */
export async function disableViaSheet(page: Page, key: string) {
  await gotoPrivat(page, `/privat/apps/${key}`);
  await page.getByTestId("disable-app").click();
  await page.getByTestId("disable-confirm").click();
  await expect(page).toHaveURL(/\/privat\/apps$/);
  await expect(page.getByTestId("toast")).toBeVisible();
}
