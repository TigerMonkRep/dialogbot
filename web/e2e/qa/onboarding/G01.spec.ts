import { expect, test } from "@playwright/test";
import { DEMO_PASSWORD, freshOwner } from "../../helpers";
import { BASE, CSRF, api, colleague, completeProfile, noOverflow, routeOAuthToApi, setGoals, snap } from "./e2b";

/* QA G01 (E2B) – /app/setup → one next action (redirect to /opsaetning/<trin>), honest progress (stepper), save/resume.
 * Since 12/11 (Fürster) the steps follow the chosen channels: Virksomhed → Viden → Telefon/Chat → (Kalender) → Betaling.
 * Krav: "Personalised setup home, one next action, honest progress, dependencies, save/resume and repair states."
 * Kilde: web/src/app/app/(guide)/setup/page.tsx, web/src/lib/setup.server.ts, web/src/components/setup-shell.tsx. */
const ID = "G01";

test("G01 · /app/setup sender til præcis næste trin; ny session genoptager; færdig → I dag", async ({ page, browser }, info) => {
  const { wsId, email } = await freshOwner(page, info);
  await page.context().clearCookies({ name: "db_setup_later" });
  await page.goto("/app/setup");
  await expect(page).toHaveURL(/\/opsaetning\/virksomhed$/);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/opsaetning\/virksomhed$/);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: true });
  // resume in a completely new browser session
  const ctx = await browser.newContext({ baseURL: BASE, viewport: info.project.use.viewport ?? undefined });
  const p2 = await ctx.newPage();
  await p2.goto("/login");
  await p2.getByLabel("E-mail").fill(email);
  await p2.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await p2.getByRole("button", { name: "Log ind" }).click();
  await p2.waitForURL((u) => !u.pathname.startsWith("/login"));
  await p2.goto("/app/setup");
  await expect(p2).toHaveURL(/\/opsaetning\/viden$/);
  // stepper: trin 1 done (check), trin 2 (Viden) current; Telefon and Kalender follow from the choices
  await expect(p2.getByRole("link", { name: "Trin 2: Viden" })).toHaveAttribute("aria-current", "step");
  await expect(p2.getByRole("link", { name: /^Trin 1: Virksomhed/ })).toHaveAccessibleName(/fuldført/);
  await expect(p2.getByRole("link", { name: /^Trin 4: Kalender/ })).toBeVisible();
  await snap(p2, ID, info, "genoptag-trin2");
  await noOverflow(p2);
  await ctx.close();
  // «senere»: I dag shows the one next action as a banner
  await page.context().addCookies([{ name: "db_setup_later", value: "1", url: BASE }]);
  await page.goto("/app");
  await expect(page.getByText(/Opsætningen er ikke færdig · næste: Viden/)).toBeVisible();
  await snap(page, ID, info, "i-dag-banner");
});

test("G01 · ærlig fremdrift: forbundet kalender vises som færdigt trin – også set fra de andre trin", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { booking: true });
  await routeOAuthToApi(page);
  await page.goto("/opsaetning/2"); // old address → Kalender
  await expect(page).toHaveURL(/\/opsaetning\/kalender$/);
  await page.getByRole("button", { name: "Forbind" }).first().click();
  await expect(page).toHaveURL(/connected=google_calendar/, { timeout: 15_000 });
  const step2Link = (p: typeof page) => p.getByRole("link", { name: /^Trin \d: Kalender/ });
  await page.goto("/opsaetning/betaling");
  await snap(page, ID, info, "trin3-stepper");
  // done steps show a check icon instead of the number
  const html = await step2Link(page).innerHTML();
  expect(html, "trin 2 vises som ikke-færdigt i trinlinjen, selvom kalenderen er forbundet").toContain("check");
});

test("G01 · læser i et ufærdigt arbejdsrum: /app må ikke ende på en side der crasher", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  const r = await colleague(page, browser, info, wsId, "reader", false);
  const voices = await api(r.page).get(`/workspaces/${wsId}/voices`);
  test.info().annotations.push({ type: "reader-voices", description: String(voices.status) });
  await r.page.goto("/app");
  await r.page.waitForLoadState("networkidle");
  await snap(r.page, ID, info, "laeser-app");
  const url = r.page.url();
  await expect(r.page.getByRole("heading", { name: /couldn.t load|Application error|Noget gik galt/i }), `læser sendt til ${url} – siden crasher (GET voices = ${voices.status})`).toHaveCount(0);
  await r.ctx.close();
});

test("G01 · trinlinjen er tilgængelig: kun de relevante trin med navn, aktuelt trin markeret, ingen vandret scroll", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  await page.goto("/opsaetning/1");
  const nav = page.getByRole("navigation", { name: "Opsætning" });
  await expect(nav.getByRole("link")).toHaveCount(4);
  await expect(nav.getByRole("link", { name: "Trin 1: Virksomhed" })).toHaveAttribute("aria-current", "step");
  for (const name of ["Trin 2: Viden", "Trin 3: Telefon", "Trin 4: Betaling"]) await expect(nav.getByRole("link", { name })).toBeVisible();
  await expect(nav.getByRole("link", { name: /sprunget over|Kalender|Chat/ })).toHaveCount(0);
  await noOverflow(page);
  void CSRF;
});

test("G01 · ærlig fremdrift: webchat + booking valgt, intet tændt/forbundet → opsætningen må ikke regnes som færdig", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: true });
  await page.context().clearCookies({ name: "db_setup_later" });
  await page.goto("/app/setup");
  await snap(page, ID, info, "webchat-booking-ikke-sat-op");
  const web = (await api(page).get(`/workspaces/${wsId}/webchat`)).body;
  expect(web.enabled).toBe(false);
  expect(page.url(), "webchat er slukket og kalenderen ikke forbundet, men /app/setup sender til I dag som færdig").toMatch(/\/opsaetning\/(viden|chat|kalender)$/);
});
