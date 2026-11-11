import { expect, type Page, type TestInfo } from "@playwright/test";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { CSRF, privatUser, startTrial } from "../../privat/pq-helpers";

/** PX (Privat-dybderunde fase 2: i18n/a11y, integrations, voice). Stack: web :3400 → API :8400 (qa_privat_stack).
 *  Run: cd web && BASE_URL=http://localhost:3400 QA_PRIV_API=http://localhost:8400 npx playwright test
 *       e2e/qa/privat-deep/x --workers=1 --output=/home/claude/pd-results/PX */
export const API = process.env.QA_PRIV_API ?? "http://localhost:8400";
export const BASE = process.env.BASE_URL ?? "http://localhost:3400";
export const AXE = process.env.AXE_PATH ?? "/home/claude/axe/node_modules/axe-core/axe.min.js";
export const EVID = join(__dirname, "../../../../../qa/evidence/PX");
export const LOCALES = ["da", "en", "de", "es", "fr", "it", "no", "sv"] as const;
export type L = (typeof LOCALES)[number];
export const HTML_LANG: Record<L, string> = { da: "da", en: "en", de: "de", es: "es", fr: "fr", it: "it", no: "nb", sv: "sv" };

export const APP_ROUTES = ["/privat/dag", "/privat/samtale", "/privat/opgaver", "/privat/apps", "/privat/butik",
  "/privat/butik/ring-for-mig", "/privat/butik/pakker", "/privat/folk", "/privat/konto", "/privat/kalender",
  "/privat/apps/ring-for-mig"] as const;
export const PUBLIC_ROUTES = ["/privat", "/privat/start/1", "/privat/offline"] as const;

export function evidence(name: string, data: unknown) {
  mkdirSync(EVID, { recursive: true });
  writeFileSync(join(EVID, name), typeof data === "string" ? data : JSON.stringify(data, null, 2));
}

let ip = 0;
export async function uniqueIp(page: Page) {
  ip += 1;
  await page.context().setExtraHTTPHeaders({ "x-real-ip": `10.77.${Math.floor(Math.random() * 200)}.${(ip % 250) + 1}` });
}

/** A Plus-trial user, logged in in this page's context, with Privat locale cookie set. */
export async function plusUser(page: Page, info: TestInfo, tag: string, locale: L = "da") {
  await uniqueIp(page);
  await setLocale(page, locale);
  const u = await privatUser(page, info, `px-${tag}`);
  await startTrial(page);
  return u;
}

export async function setLocale(page: Page, locale: L) {
  await page.context().addCookies([{ name: "dlg_lang", value: locale, url: BASE }]);
}

export async function go(page: Page, path: string) {
  await page.goto(path, { waitUntil: "domcontentloaded", timeout: 25_000 }).catch(() => {});
  await settle(page);
}

export async function settle(page: Page) {
  await page.waitForLoadState("load", { timeout: 6_000 }).catch(() => {});
  const busy = page.locator("[data-busy]").first();
  if (await busy.count()) await expect(busy).toHaveAttribute("data-busy", "false", { timeout: 8_000 }).catch(() => {});
  await page.waitForTimeout(500);
}

export async function runAxe(page: Page) {
  if (!existsSync(AXE)) return null;
  await page.addScriptTag({ path: AXE });
  return page.evaluate(async () => {
    // @ts-ignore injected
    const res = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } });
    return res.violations.map((v: { id: string; impact: string; help: string; nodes: { target: string[]; html: string }[] }) => ({
      id: v.id, impact: v.impact, help: v.help, n: v.nodes.length, targets: v.nodes.slice(0, 4).map((n) => n.target.join(" ")),
      html: v.nodes.slice(0, 2).map((n) => n.html.slice(0, 160)) }));
  });
}

export { CSRF };

export function within<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([p, new Promise<T>((r) => setTimeout(() => r(fallback), ms))]);
}
