import { readFileSync } from "node:fs";
import { expect, type Page, type TestInfo } from "@playwright/test";
import { QA_API } from "./pq-helpers";

/** P2 (e2e-privat, wave 2) helpers on top of pq-helpers. Run against tests/qa/qa_privat_stack.py:
 *    QA_PRIV_PORT=8300 QA_PRIV_FRONT=http://localhost:3300 QA_PRIV_DB=…/qa_p1priv_stack python -m tests.qa.qa_privat_stack \
 *      > /home/claude/p1-results/P2-run/api.log 2>&1
 *    cd web && API_BASE_URL=http://localhost:8300 PREVIEW_GATE=off npx next start -p 3300
 *    BASE_URL=http://localhost:3300 QA_PRIV_API=http://localhost:8300 QA_PRIV_LOG=/home/claude/p1-results/P2-run/api.log \
 *      npx playwright test e2e/qa/privat/X04.spec.ts … --output=/home/claude/p1-results/P2 --workers=1
 *  The funnel's SMS code is simulated (connectors/fakes.fake_send_sms): it never leaves the process and is only in the
 *  API's log (event sms.simulated) – read from QA_PRIV_LOG. */
export const API_LOG = process.env.QA_PRIV_LOG ?? "/home/claude/p1-results/P2-run/api.log";

export const uniqueIp = () => `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${1 + Math.floor(Math.random() * 250)}`;
/** A Danish mobile number nobody else in this run uses (2x xx xx xx). */
export const uniqueMobile = () => `2${String(Math.floor(Math.random() * 1e7)).padStart(7, "0")}`;

/** The last simulated SMS to `e164` in the API log. */
export async function lastSmsTo(e164: string, timeoutMs = 10_000): Promise<string> {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const lines = readFileSync(API_LOG, "utf8").split("\n").filter((l) => l.includes('"sms.simulated"') && l.includes(`"to": "${e164}"`));
    if (lines.length) return JSON.parse(lines[lines.length - 1]).body as string;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`no simulated SMS to ${e164} in ${API_LOG}`);
}

export async function shot(page: Page, info: TestInfo, scenario: string, name: string) {
  const path = `../qa/evidence/${scenario}/P2-${info.project.name}-${name}.png`;
  await page.screenshot({ path, fullPage: true });
  await info.attach(name, { path, contentType: "image/png" });
}

export async function mailbox(page: Page) {
  const r = await page.request.get(`${QA_API}/api/v1/dev/mailbox`);
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as { messages?: { to: string; subject: string; text?: string; html?: string }[] } | { to: string; subject: string }[];
}

export async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "ingen vandret scroll").toBeLessThanOrEqual(0);
}

/** Fill the fake Stripe Checkout (qa_privat_stack) with the success card and submit. */
export async function payFakeStripe(page: Page, card = "4242 4242 4242 4242") {
  await expect(page.locator("[data-testid=fake-stripe]")).toBeVisible({ timeout: 20_000 });
  const fill = async (label: string, v: string) => { const f = page.getByLabel(label, { exact: true }); if (await f.count()) { if (!(await f.inputValue())) await f.fill(v); } };
  await fill("Navn på kortholder", "Mette Jensen");
  await fill("Adresse", "Abildgade 18");
  await fill("Postnummer", "8200");
  await fill("By", "Aarhus N");
  await fill("Telefon", "+4520304050");
  await page.getByLabel("Kortnummer", { exact: true }).fill(card);
  await page.getByRole("button", { name: /prøveperiode|Betal/ }).click();
}
