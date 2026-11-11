import { expect, test } from "@playwright/test";
import { SEEDED, freshOwner, login } from "../../helpers";
import { CSRF, evid, noStaging } from "./e2c-helpers";

/* K01 /app/knowledge (→ /app/viden): "Approved business facts, sources, catalogue, offers and review queue summary." */

const OFFER = { discount_percent: 15, condition: { area_operator: "gte", area_threshold_m2: 40 }, starts_on: "2026-10-01", ends_on_inclusive: "2026-11-30" };

test("K01 · tom viden → forslag i kø → godkend i browseren: kø, godkendt viden og assistentens viden stemmer", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info, "reception");
  await page.goto("/app/viden");
  await expect(page.getByRole("heading", { name: "Alt, Dialogbot må sige til jeres kunder" })).toBeVisible();
  await expect(page.getByText("Ingen ydelser endnu – uden dem kan den ikke svare på priser.")).toBeVisible(); // empty state
  await expect(page.getByRole("button", { name: /Hent fra hjemmesiden/ })).toBeVisible(); // sources
  const before = (await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json()).items.length;
  // three proposals waiting for review (as an import or a staff member would leave them)
  const mk = async (kind: string, title: string, content: Record<string, unknown>) => {
    const it = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind, title, content } })).json();
    expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${it.open_draft.id}/submit`, { headers: CSRF })).ok()).toBeTruthy();
    return it;
  };
  await mk("service", "Gulvafslibning", { description: "Fra 245 kr. pr. m²", unit: "m2", price_net_minor: 24500, currency: "DKK", promote: true });
  await mk("offer", "Efterårsrabat på gulvafslibning", OFFER);
  await mk("fact", "Vi har 25 års erfaring", { text: "Vi har 25 års erfaring med trægulve." });
  const queue = (await (await page.request.get(`/api/backend/workspaces/${wsId}/knowledge/review-queue`)).json()) as unknown[];
  expect(queue).toHaveLength(3);
  await page.reload();
  await expect(page.getByText(`${2} forslag venter`)).toBeVisible(); // «Det I sælger»: service + offer
  const cards = page.getByRole("button", { name: "Godkend", exact: true });
  await expect(cards).toHaveCount(queue.length);
  await page.screenshot({ path: evid("K01", info, "koe"), fullPage: true });
  // approve the offer
  const offerCard = page.locator("div.border-dashed").filter({ hasText: "Efterårsrabat på gulvafslibning" }).filter({ has: page.getByRole("button", { name: "Godkend", exact: true }) }).last();
  await offerCard.getByRole("button", { name: "Godkend", exact: true }).dblclick(); // double submit: idempotency key
  await expect(page.getByText("-15% ved ≥ 40 m²", { exact: false })).toBeVisible();
  await page.reload();
  await expect(page.getByText("1 forslag venter")).toBeVisible();
  expect(((await (await page.request.get(`/api/backend/workspaces/${wsId}/knowledge/review-queue`)).json()) as unknown[]).length).toBe(2);
  const live = (await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json()).items as { kind: string; title: string }[];
  expect(live.length).toBe(before + 1);
  expect(live.filter((i) => i.kind === "offer").map((i) => i.title)).toEqual(["Efterårsrabat på gulvafslibning"]);
  expect(await page.locator("body").innerText()).not.toMatch(/>\s?40|over ?40/);
  await noStaging(page);
});

test("K01 · roller: læser ser viden men kan ikke rette, godkende eller oprette; API afviser", async ({ page }, info) => {
  await login(page, SEEDED.reader);
  const ws = (await (await page.request.get("/api/backend/workspaces")).json())[0].id as string;
  await page.goto("/app/viden");
  await expect(page.getByText("Efterårsrabat på gulvafslibning")).toBeVisible();
  await expect(page.getByText("-15% ved ≥ 40 m²", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Ret$|Godkend|Tilføj et tilbud|Hent fra hjemmesiden/ })).toHaveCount(0);
  await page.screenshot({ path: evid("K01", info, "laeser"), fullPage: true });
  const r = await page.request.post(`/api/backend/workspaces/${ws}/knowledge/items`, { headers: CSRF, data: { kind: "fact", title: `QA-E2C læser ${Date.now()}`, content: { text: "x" } } });
  expect(r.status()).toBe(403);
});
