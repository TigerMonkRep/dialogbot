import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, type TestInfo } from "@playwright/test";
import { PREVIEW_CODE } from "../../helpers";

/* Shared bits for QA wave 2 (P1), instance A (prefix E2A). */
export const CSRF = { "x-requested-with": "dialogbot" };
/** The web origin under test (same default as playwright.config.ts baseURL; the local QA stack sets BASE_URL=:3200). */
export const WEB = new URL(process.env.BASE_URL ?? "http://localhost:3000").origin;
/** The API's log, where the fake SMS adapter writes its codes. CI: e2e.yml sets P1_API_LOG (the stack writes api.log
 *  in the repository root, which is also the default here); the local QA stack sets its own path. */
export const API_LOG = process.env.P1_API_LOG ?? resolve(__dirname, "../../../../api.log");

/** Evidence folder qa/evidence/<id>/ (relative to web/). */
export function evid(id: string) {
  const dir = `../qa/evidence/${id}`;
  mkdirSync(dir, { recursive: true });
  return dir;
}

export async function snap(page: Page, info: TestInfo, id: string, name: string) {
  await page.screenshot({ path: `${evid(id)}/${info.project.name}-${name}.png`, fullPage: true });
}

/** The preview gate (PREVIEW_GATE=on) covers /, /erhverv, /proev, /byggevejledning and /signup. */
export async function unlock(page: Page) {
  expect((await page.request.post("/api/preview/unlock", { headers: CSRF, data: { code: PREVIEW_CODE, next: "/" } })).ok()).toBeTruthy();
}

/** A unique visitor IP per test (the funnels and the demo endpoints have per-IP limits). */
export function uniqueIp() {
  const n = Date.now() + Math.floor(Math.random() * 1e6);
  return `10.${(n >> 16) & 255}.${(n >> 8) & 255}.${n & 255}`;
}

/** A unique Danish mobile number, 8 digits, starting with 2. */
export function uniqueMobile() {
  const d = String(Date.now() % 10_000_000).padStart(7, "0");
  return `2${d}`;
}

/** The simulated SMS code for a number: the fake SMS adapter only logs it (app/modules/integrations/connectors/fakes.py). */
export async function smsCodeFor(e164: string): Promise<string> {
  let code: string | undefined;
  await expect.poll(() => {
    const log = readFileSync(API_LOG, "utf8");
    const lines = log.split("\n").filter((l) => l.includes("sms.simulated") && l.includes(e164));
    const m = lines.at(-1)?.match(/er (\d{6})\./);
    code = m?.[1];
    return code;
  }, { timeout: 15_000 }).toBeTruthy();
  return code!;
}

/** No horizontal scroll at the current viewport. */
export async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "ingen vandret scroll").toBeLessThanOrEqual(1);
}

/** Sections (top-level <section> elements in <main>) that show more than one primary button: a visible link or button
 *  filled with the accent colour (#2456F6). docs/brand.md: one primary button per screen/section. */
export async function sectionsWithSeveralPrimaries(page: Page) {
  return page.evaluate(() => {
    const ACCENT = "rgb(36, 86, 246)";
    const out: string[] = [];
    document.querySelectorAll("main section").forEach((sec) => {
      if (sec.parentElement?.closest("main section")) return; // top-level only
      const prim = Array.from(sec.querySelectorAll("a,button")).filter((e) => {
        const r = (e as HTMLElement).getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(e).backgroundColor === ACCENT;
      }).map((e) => (e.textContent ?? "").trim().slice(0, 40));
      if (prim.length > 1) out.push(`${(sec.querySelector("h1,h2")?.textContent ?? sec.id ?? "?").trim().slice(0, 50)}: ${prim.join(" | ")}`);
    });
    return out;
  });
}

/** Every same-origin link on the page answers below 400 (redirects followed). */
export async function internalLinksOk(page: Page) {
  const hrefs = await page.$$eval("a[href^='/']", (as) => Array.from(new Set(as.map((a) => a.getAttribute("href")!.split("#")[0]))).filter(Boolean));
  const bad: string[] = [];
  for (const h of hrefs) {
    const r = await page.request.get(h, { maxRedirects: 5 });
    if (r.status() >= 400) bad.push(`${h} → ${r.status()}`);
  }
  return bad;
}

/** Data-only update on the QA stack's database (never structural): make this test user's open tokens of one purpose
 *  expire, as if the TTL had passed. Only ever called for e-mails the test itself registered. */
export function expireTokens(email: string, purpose: "verify_email" | "password_reset") {
  if (!/^e2a-[\w.-]+@example\.com$/.test(email)) throw new Error("only QA users created by this suite");
  const db = (process.env.DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/dialogbot_p1").replace("+psycopg", "");
  const sql = `update auth_tokens set expires_at = now() - interval '1 hour' where used_at is null and purpose = '${purpose}' and user_id = (select id from users where email_normalized = '${email.toLowerCase()}')`;
  const out = require("node:child_process").execFileSync("psql", [db, "-tAc", sql], { encoding: "utf8" }) as string;
  return out.trim();
}

/** All simulated mails for the logged-in user. */
export async function mailbox(page: Page): Promise<{ subject: string; body_text: string }[]> {
  const r = await page.request.get("/api/backend/dev/mailbox");
  return r.ok() ? (await r.json()).items : [];
}
