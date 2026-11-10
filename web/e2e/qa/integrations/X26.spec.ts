import { expect, test, type Page } from "@playwright/test";
import { freshOwner, shot } from "../../helpers";

/* X26 (integrations-qa): the UI shows exactly the status the API computes, for every connector – nothing green that
 * is not connected, every simulated connection marked «(simuleret)», «På vej» items without a connect button. Runs
 * against the full stack with fake adapters (CONNECTORS_PROVIDER=fake); nothing leaves the machine. */

const CSRF = { "x-requested-with": "dialogbot" };
const LABEL: Record<string, string> = { connected: "Forbundet", not_connected: "Ikke forbundet", error: "Fejl", not_implemented: "Ikke tilgængelig" };
type Item = { key: string; label: string; status: string; simulated: boolean; availability: string; zapier_note: string };

async function catalogue(page: Page, wsId: string) {
  const r = await page.request.get(`/api/backend/workspaces/${wsId}/integrations`, { headers: CSRF });
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as { items: Item[]; simulated: boolean };
}

async function expectParity(page: Page, wsId: string) {
  const cat = await catalogue(page, wsId);
  for (const c of cat.items.filter((i) => i.availability === "ready")) {
    const card = page.locator(`[data-connector="${c.key}"]`);
    const want = LABEL[c.status] + ((c.status === "connected" || c.status === "error") && c.simulated ? " (simuleret)" : "");
    await expect(card.locator("h3 + span"), `${c.key}: API status ${c.status}`).toHaveText(want);
    if (c.status === "not_implemented") await expect(card.getByRole("button", { name: "Forbind" })).toHaveCount(0);
  }
  for (const c of cat.items.filter((i) => i.availability !== "ready")) {
    expect(c.status, c.key).toBe("not_implemented");
    await expect(page.locator(`[data-connector="${c.key}"]`)).toHaveCount(0); // listed as text, never as a card
    await expect(page.locator("li", { hasText: c.label }).filter({ hasNot: page.getByRole("button") }).first()).toBeVisible();
  }
  return cat;
}

test("X26 · Integrationer: UI = API for hver connector, simuleret mærket, intet grønt der ikke er forbundet", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=integrationer");
  await expect(page.getByRole("heading", { name: "Handlinger i jeres egne systemer" })).toBeVisible();
  const cat = await expectParity(page, wsId);
  expect(cat.simulated).toBe(true);
  await expect(page.getByText(/Testmiljø: forbindelser og handlinger er simulerede/)).toBeVisible();
  expect(cat.items.filter((i) => i.status === "connected")).toEqual([]); // fresh workspace: nothing green
  await expect(page.getByText("Forbundet", { exact: true })).toHaveCount(0);
  await shot(page, info, "x26-integrationer-tom");

  // Connect Google (simulated OAuth round-trip) and SMS; parity must still hold, both marked simulated.
  await page.locator('[data-connector="google_calendar"]').getByRole("button", { name: "Forbind" }).click();
  await expect(page.getByText("Google Kalender er forbundet.")).toBeVisible();
  await page.goto("/app/indstillinger?ark=integrationer");
  await page.locator('[data-connector="twilio_sms"]').getByRole("button", { name: "Forbind" }).click();
  await expect(page.locator('[data-connector="twilio_sms"]').getByText("Forbundet (simuleret)")).toBeVisible();
  const after = await expectParity(page, wsId);
  expect(after.items.filter((i) => i.status === "connected").map((i) => [i.key, i.simulated]).sort())
    .toEqual([["google_calendar", true], ["twilio_sms", true]]);
  await page.locator('[data-connector="google_calendar"]').getByRole("button", { name: "Test forbindelse" }).click();
  await expect(page.getByText("Forbindelsen virker (simuleret).")).toBeVisible();
  await shot(page, info, "x26-integrationer-forbundet");

  // Reload keeps the same honest state.
  await page.reload();
  await expectParity(page, wsId);
});

test("X26 · Alle indstillinger: tiles for forbundne systemer siger «simuleret», når forbindelsen er simuleret", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=integrationer");
  await page.locator('[data-connector="google_calendar"]').getByRole("button", { name: "Forbind" }).click();
  await expect(page.getByText("Google Kalender er forbundet.")).toBeVisible();
  const g = (await catalogue(page, wsId)).items.find((i) => i.key === "google_calendar")!;
  expect(g.status).toBe("connected");
  expect(g.simulated).toBe(true);
  await page.goto("/app/indstillinger");
  const row = page.locator("li", { has: page.getByText("Forbundne systemer", { exact: true }) });
  await expect(row).toContainText("Google Kalender");
  await shot(page, info, "x26-indstillinger-tiles");
  // F-IQ-07: the tile says «Klar» (= «virker nu») and never says the connection is simulated.
  await expect(row, "simulated connection shown as «Klar» without «simuleret»").toContainText(/simuleret/i);
});
