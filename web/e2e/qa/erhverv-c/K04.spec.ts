import { expect, test } from "@playwright/test";
import { SEEDED, freshOwner, login } from "../../helpers";
import { CSRF, evid } from "./e2c-helpers";

/* K04 /app/knowledge/offers (→ /app/viden «Tilbud og rabatter»): "Dated offers, conditions, scope,
   draft/active/expired states and detail editor." Business rule: the offer applies at >= 40 m² (DB-005). */

const OFFER = { discount_percent: 15, condition: { area_operator: "gte", area_threshold_m2: 40 }, starts_on: "2026-10-01", ends_on_inclusive: "2026-11-30" };

async function eligible(req: import("@playwright/test").APIRequestContext, ws: string, id: string, area: number | null, on: string) {
  const r = await req.get(`/api/backend/workspaces/${ws}/knowledge/offers/${id}/eligibility?on_date=${on}${area === null ? "" : `&area_m2=${area}`}`);
  expect(r.ok(), await r.text()).toBeTruthy();
  return (await r.json()).eligible as boolean;
}

test("K04 · opret tilbud i browseren: ≥ 40 m², datoer inkl., overlever reload; reglen 39/40/41/1. dec. holder", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info, "reception");
  await page.goto("/app/viden");
  await page.getByRole("button", { name: "+ Tilføj et tilbud" }).click();
  await page.getByLabel("Hvad hedder tilbuddet?").fill("Efterårsrabat på gulvafslibning");
  await page.getByLabel("Rabat (%)").fill("15");
  await expect(page.getByLabel("Gælder ved mindst (m²)")).toHaveValue("40");
  await page.getByLabel("Fra", { exact: true }).fill("2026-10-01");
  await page.getByLabel("Til og med").fill("2026-11-30");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  const row = page.locator("div").filter({ hasText: /^Efterårsrabat på gulvafslibning · -15% ved ≥ 40 m²/ }).first();
  await expect(page.getByText("-15% ved ≥ 40 m²", { exact: false })).toBeVisible();
  await expect(page.getByText(/begge dage inkl\./)).toBeVisible();
  await page.reload();
  await expect(page.getByText("-15% ved ≥ 40 m²", { exact: false })).toBeVisible();
  void row;
  const items = (await (await page.request.get(`/api/backend/workspaces/${wsId}/knowledge/items?kind=offer`)).json()).items;
  expect(items).toHaveLength(1);
  const v = items[0].approved_version;
  expect(v.content).toMatchObject(OFFER);
  const id = items[0].id;
  expect(await eligible(page.request, wsId, id, 39, "2026-11-10")).toBe(false);
  expect(await eligible(page.request, wsId, id, 40, "2026-11-10")).toBe(true);
  expect(await eligible(page.request, wsId, id, 41, "2026-11-10")).toBe(true);
  expect(await eligible(page.request, wsId, id, 40, "2026-11-30")).toBe(true);
  expect(await eligible(page.request, wsId, id, 40, "2026-12-01")).toBe(false);
  // the detail editor shows the same condition
  const offerRow = page.locator("div.flex-wrap").filter({ hasText: "Efterårsrabat på gulvafslibning" }).filter({ has: page.getByRole("button", { name: "Ret" }) }).last();
  await offerRow.getByRole("button", { name: "Ret" }).click();
  await expect(page.getByLabel("Gælder ved mindst (m²)")).toHaveValue("40");
  await expect(page.getByLabel("Til og med")).toHaveValue("2026-11-30");
  expect(await page.locator("body").innerText()).not.toMatch(/>\s?40|over ?40/);
  await page.screenshot({ path: evid("K04", info, "tilbud-oprettet"), fullPage: true });
});

test("K04 · tilbud uden datoer: fejlbeskeden er forståelig dansk (ikke feltnavne)", async ({ page }, info) => {
  test.fail(true, "F-E2C-08-K04: S2 new – Gem et tilbud uden datoer → fejlboksen viser «starts_on skal være en ISO-dato» – teknisk …");
  const { wsId } = await freshOwner(page, info, "reception");
  await page.goto("/app/viden");
  await page.getByRole("button", { name: "+ Tilføj et tilbud" }).click();
  await page.getByLabel("Hvad hedder tilbuddet?").fill("Rabat uden datoer");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  const err = page.locator("main [role=alert]").first();
  await expect(err).toBeVisible();
  await page.screenshot({ path: evid("K04", info, "uden-datoer"), fullPage: true });
  await expect(err).not.toContainText(/starts_on|ends_on|ISO/);
  expect((await (await page.request.get(`/api/backend/workspaces/${wsId}/knowledge/items?kind=offer`)).json()).items).toHaveLength(0);
});

test("K04 · tilstande: udløbet tilbud vises som udløbet, ikke som aktivt", async ({ page }, info) => {
  test.fail(true, "F-E2C-06-K04: S2 new – «Tilbud og rabatter» viser ikke tilstand: et udløbet tilbud står præcis som et aktivt (ingen …");
  const { wsId } = await freshOwner(page, info, "reception");
  const it = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "offer", title: "Sommerrabat", content: { ...OFFER, starts_on: "2026-06-01", ends_on_inclusive: "2026-08-31" } } })).json();
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${it.open_draft.id}/approve`, { headers: { ...CSRF, "idempotency-key": `qa-e2c-${it.open_draft.id}` } })).ok()).toBeTruthy();
  await page.goto("/app/viden");
  const row = page.locator("div.flex-wrap").filter({ hasText: "Sommerrabat" }).last();
  await expect(row).toBeVisible();
  await page.screenshot({ path: evid("K04", info, "udloebet-tilbud"), fullPage: true });
  await expect(row).toContainText(/udløbet/i);
});

test("K04 · medarbejder foreslår tilbud → kladde venter, er ikke i assistentens viden; ejer kan genoprette fjernet tilbud med samme navn", async ({ page }, info) => {
  await login(page, SEEDED.staff);
  const ws = (await (await page.request.get("/api/backend/workspaces")).json())[0].id as string;
  const title = `QA-E2C forslag ${info.project.name} ${Date.now()}`;
  await page.goto("/app/viden");
  await page.getByRole("button", { name: "+ Tilføj et tilbud" }).click();
  await page.getByLabel("Hvad hedder tilbuddet?").fill(title);
  await page.getByLabel("Fra", { exact: true }).fill("2026-11-01");
  await page.getByLabel("Til og med").fill("2026-11-30");
  await page.getByRole("button", { name: "Send til godkendelse" }).click();
  await expect(page.getByText("Sendt til godkendelse", { exact: false }).first()).toBeVisible();
  const items = (await (await page.request.get(`/api/backend/workspaces/${ws}/knowledge/items?kind=offer&limit=200`)).json()).items as { id: string; open_draft: { title: string; status: string } | null; approved_version: unknown }[];
  const mine = items.find((i) => i.open_draft?.title === title)!;
  expect([mine.open_draft!.status, mine.approved_version]).toEqual(["in_review", null]);
  const live = (await (await page.request.get(`/api/backend/workspaces/${ws}/assistant/knowledge`)).json()).items as { title: string }[];
  expect(live.map((i) => i.title)).not.toContain(title);
  await page.reload();
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByText("Afventer godkendelse hos en ejer eller administrator").first()).toBeVisible();
  // owner: approve, remove, and add the same offer again
  await page.context().clearCookies();
  await login(page, SEEDED.owner);
  const ver = (await (await page.request.get(`/api/backend/workspaces/${ws}/knowledge/items/${mine.id}`)).json()).open_draft.id;
  expect((await page.request.post(`/api/backend/workspaces/${ws}/knowledge/versions/${ver}/approve`, { headers: { ...CSRF, "idempotency-key": `qa-e2c-${ver}` } })).ok()).toBeTruthy();
  expect((await page.request.delete(`/api/backend/workspaces/${ws}/knowledge/items/${mine.id}`, { headers: CSRF })).status()).toBe(204);
  const again = await page.request.post(`/api/backend/workspaces/${ws}/knowledge/items`, { headers: CSRF, data: { kind: "offer", title, content: OFFER } });
  const status = again.status();
  if (again.ok()) await page.request.delete(`/api/backend/workspaces/${ws}/knowledge/items/${(await again.json()).id}`, { headers: CSRF });
  expect(status, `re-adding a removed offer named ${title}: ${status}`).toBe(201);
});
