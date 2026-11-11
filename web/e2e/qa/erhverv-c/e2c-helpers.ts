import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* QA wave 2 (P1), e2e-erhverv instance C: shared setup for C02-C14 and K01/K04. Prices are never asserted. */
export const CSRF = { "x-requested-with": "dialogbot" };
export const CONSENT = "Tilmelding på hjemmesiden, marts 2026";

export function evid(id: string, info: TestInfo, name: string) {
  const dir = `../qa/evidence/${id}`;
  mkdirSync(dir, { recursive: true });
  return `${dir}/${info.project.name}-${name}.png`;
}

/** Fresh owner + workspace (intent «both») with «ringe kunder op» switched on, so /app/kampagner shows campaigns.
 *  NB: a «campaigns»-only workspace cannot switch it on at all – see F-E2C-01-C02. */
export async function campaignOwner(page: Page, info: TestInfo) {
  const { wsId, email } = await freshOwner(page, info, "both");
  const goals = await (await page.request.get(`/api/backend/workspaces/${wsId}/goals`)).json();
  const { version, ...g } = goals;
  const r = await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...g, callback: true, expected_version: version } });
  expect(r.ok(), await r.text()).toBeTruthy();
  return { wsId, email };
}

export async function newCampaign(req: APIRequestContext, wsId: string, name: string, extra: Record<string, unknown> = {}) {
  const r = await req.post(`/api/backend/workspaces/${wsId}/campaigns`, { headers: CSRF, data: { name, purpose: "Tilbyde gulvafslibning til tidligere kunder", ...extra } });
  expect(r.status(), await r.text()).toBe(201);
  return r.json();
}

export async function importCsv(req: APIRequestContext, wsId: string, id: string, csv: string, kind = "business") {
  const r = await req.post(`/api/backend/workspaces/${wsId}/campaigns/${id}/contacts/import`, { headers: CSRF, data: { csv, kind, consent_source: CONSENT } });
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
}

export async function getCampaign(req: APIRequestContext, wsId: string, id: string) {
  return (await req.get(`/api/backend/workspaces/${wsId}/campaigns/${id}`)).json();
}

/** Data-only update of OUR OWN campaign rows in the shared stack (no structural change). Used to show the states a
 *  real dialler run produces (running, outcomes) – the stack has no VAPI key, so the worker skips these campaigns
 *  (`outbound_problem`) and nobody is ever called. */
export function sql(statement: string) {
  const url = (process.env.DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/dialogbot_p1").replace("+psycopg", "");
  return execFileSync("psql", [url, "-v", "ON_ERROR_STOP=1", "-Atc", statement], { encoding: "utf8" });
}

/** Number of visible primary (accent) buttons on the page – brand.md: «Én primær knap pr. skærm». */
export async function primaryButtons(page: Page) {
  return page.locator("main button.bg-accent:visible, main a.bg-accent:visible").count();
}

export async function noStaging(page: Page) {
  expect(await page.locator("body").innerText()).not.toMatch(/staging/i);
}

/** The value of one counter tile on the campaign page («Kontakter», «Talt med», «Tilbage» …). */
export function stat(page: Page, label: string) {
  return page.locator("dl > div").filter({ has: page.locator("dt", { hasText: new RegExp(`^${label}$`) }) }).locator("dd");
}
