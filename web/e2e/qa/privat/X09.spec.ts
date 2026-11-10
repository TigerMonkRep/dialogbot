import { expect, test, type Page } from "@playwright/test";
import { CSRF, evidence, needsPrivatStack, privatUser, say, startTrial, waitIdle } from "./pq-helpers";

/** X09 (P0): Ønskeliste – reservationer er aldrig synlige for ejeren (UI + hvert JSON-svar siden henter); en modtager
 *  uden abonnement kan åbne den delte ønskeliste og ellers næsten intet (direkte URL'er og API-kald). Real Privat backend
 *  (tests/qa/qa_privat_stack.py). The rest of the API surface: tests/qa/test_qa_privat_x09.py. */

test.beforeEach(async ({ request }) => {
  test.skip(!(await needsPrivatStack(request)), "kræver tests/qa/qa_privat_stack.py på :8100 og next på BASE_URL med API_BASE_URL=:8100");
});

/** Every JSON body the page receives from /api/backend while `fn` runs. */
async function captureJson(page: Page, fn: () => Promise<void>) {
  const bodies: string[] = [];
  const on = async (r: import("@playwright/test").Response) => {
    if (!r.url().includes("/api/backend/")) return;
    try { bodies.push(await r.text()); } catch { /* redirects, aborted */ }
  };
  page.on("response", on);
  await fn();
  await page.waitForLoadState("networkidle");
  page.off("response", on);
  return bodies;
}

test("ønskeliste: modtager uden plan reserverer via linket; ejeren ser intet i UI eller JSON; modtageren når intet andet", async ({ browser, page }, info) => {
  // Owner on the trial with a wishlist and a private shopping list.
  await privatUser(page, info, "x09-owner", "Mette Hansen");
  await startTrial(page);
  const tid = (await say(page, "Lav en ønskeliste med cykelhjelm og bog"))!;
  const other = (await say(page, "Lav en indkøbsliste med mælk og rugbrød"))!;
  expect(tid && other).toBeTruthy();
  const inv = await (await page.request.post(`/api/backend/privat/tasks/${tid}/share`, { headers: CSRF, data: { mode: "wishlist", role: "editor" } })).json();

  // Recipient without any plan, in their own browser.
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined, locale: "da-DK", timezoneId: "Europe/Copenhagen" });
  const ole = await ctx.newPage();
  await privatUser(ole, info, "x09-ole", "Ole Berg");
  expect((await (await ole.request.get("/api/backend/privat/subscription")).json()).entitled).toBe(false);
  await ole.goto(`/privat/invitation/${inv.token}`);
  await expect(ole.getByText("Mette har delt en liste med dig").or(ole.getByText(/Mette/).first())).toBeVisible();
  await expect(ole.getByText("Cykelhjelm")).toHaveCount(0);  // the preview shows no wishes
  await evidence(ole, info, "X09", "recipient-invitation");
  await ole.getByRole("button", { name: "Åbn listen" }).click();
  await expect(ole).toHaveURL(new RegExp(`/privat/opgaver/${tid}`), { timeout: 20_000 });
  await waitIdle(ole);
  const helm = ole.locator("[data-testid=wish-card]:visible", { hasText: "Cykelhjelm" }).last();
  await helm.getByRole("button", { name: "Jeg køber den" }).click();
  await expect(helm.getByText("Du køber den")).toBeVisible();
  await evidence(ole, info, "X09", "recipient-reserved");

  // The owner: reload the list and the overview – nothing in the UI, nothing in any JSON the page loads.
  const bodies = await captureJson(page, async () => {
    await page.goto(`/privat/opgaver/${tid}`);
    await waitIdle(page);
    await page.reload();
    await waitIdle(page);
  });
  const card = page.locator("[data-testid=wish-card]:visible", { hasText: "Cykelhjelm" }).last();
  await expect(card).toBeVisible();
  await expect(page.getByText("Reserveret", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Du køber den")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Jeg køber den" })).toHaveCount(0);
  await evidence(page, info, "X09", "owner-after-reservation");
  expect(bodies.length).toBeGreaterThan(0);
  for (const b of bodies) {
    expect(b.replace(/\s/g, "")).not.toContain('"reserved":true');
    expect(b).not.toContain('"reserved_by_me":true');
  }

  // The recipient, by direct URL and API: the owner's other list, the Shop, own tasks, calls – no.
  await ole.goto(`/privat/opgaver/${other}`);
  await waitIdle(ole);
  await expect(ole.getByText("Rugbrød")).toHaveCount(0);
  expect((await ole.request.get(`/api/backend/privat/tasks/${other}`)).status()).toBe(404);
  expect((await ole.request.post(`/api/backend/privat/tasks/${tid}/items`, { headers: CSRF, data: { text: "Bil" } })).status()).toBe(403);
  expect((await ole.request.post(`/api/backend/privat/tasks/${tid}/share`, { headers: CSRF, data: { mode: "wishlist" } })).status()).toBeGreaterThanOrEqual(403);
  expect((await ole.request.post("/api/backend/privat/addons/ring-for-mig/enable", { headers: CSRF })).status()).toBe(409);
  expect((await ole.request.post("/api/backend/privat/addons/kalender/enable", { headers: CSRF })).status()).toBe(409);
  await ole.goto("/privat/butik/kalender");
  await waitIdle(ole);
  await expect(ole.getByTestId("enable-app")).toHaveCount(0);
  await evidence(ole, info, "X09", "recipient-shop-app");
  await ctx.close();
});
