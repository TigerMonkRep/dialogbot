import { expect, test } from "@playwright/test";
import { CSRF, needsPrivatStack, privatUser, startTrial, waitIdle } from "./pq-helpers";
import { payFakeStripe, shot } from "./p2-helpers";

/** X12 (P1): Butikken – hvert app-ikon → «Hvad den gør» → egen installér-flow; installér/afinstallér idempotent.
 *  Real backend (tests/qa/qa_privat_stack.py). API-level idempotency for every app: tests/qa/test_qa_privat_x10_x12.py. */

type Addon = { key: string; name: string; enabled: boolean; status: string; requires_plan: boolean; what: string };

test.beforeEach(async ({ request }) => {
  test.skip(!(await needsPrivatStack(request)), "kræver tests/qa/qa_privat_stack.py og next med API_BASE_URL til den");
});

test("hvert app-ikon i Butikken åbner sin egen side med «Hvad den gør» og sin egen knap", async ({ page }, info) => {
  test.setTimeout(240_000);
  await privatUser(page, info, "x12-all", "Ole Berg"); // no plan: the plan apps show the trial offer
  const apps = (await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[];
  await page.goto("/privat/butik");
  await waitIdle(page);
  await shot(page, info, "X12", "shop");
  for (const a of apps) {
    await page.goto("/privat/butik");
    await waitIdle(page);
    const row = page.locator(`[data-testid=app-row-${a.key}]:visible`).first();
    await expect(row, a.key).toBeVisible();
    await row.click();
    if (a.enabled) {
      await expect(page, a.key).toHaveURL(new RegExp(`/privat/apps/${a.key}$`));
      await expect(page.getByTestId("app-page").or(page.getByTestId("app-kept")).first()).toBeVisible();
      continue;
    }
    await expect(page, a.key).toHaveURL(new RegExp(`/privat/butik/${a.key}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(a.name);
    await expect(page.getByText("Hvad den gør", { exact: true }).first(), a.key).toBeVisible();
    await expect(page.getByText(a.what.slice(0, 40)).first(), a.key).toBeVisible();
    const action = a.status === "coming_soon" ? "notify-me" : a.requires_plan ? "needs-plan" : "enable-app";
    await expect(page.locator(`[data-testid=${action}]:visible`).first(), `${a.key} → ${action}`).toBeVisible();
  }
});

test("installér → trin 1 → afinstallér → installér igen; dobbelt-tryk og direkte link ændrer intet", async ({ page }, info) => {
  await privatUser(page, info, "x12-flow", "Mette Hansen");
  await startTrial(page);
  await page.goto("/privat/butik/madplan");
  await waitIdle(page);
  await expect(page.getByText("Hvad den gør", { exact: true }).first()).toBeVisible();
  await page.locator("[data-testid=enable-app]:visible").first().click();
  const confirm = page.getByTestId("enable-confirm");
  await expect(confirm).toBeVisible();
  await shot(page, info, "X12", "enable-sheet");
  await confirm.dblclick(); // a 60-year-old's double tap
  await expect(page.getByRole("button", { name: "Start trin 1" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Start trin 1" }).click();
  await expect(page).toHaveURL(/\/privat\/apps\/madplan$/);
  await expect(page.getByTestId("app-setup")).toBeVisible();
  // the shop link of an app that is on leads to the app, not a second install
  await page.goto("/privat/butik/madplan");
  await expect(page).toHaveURL(/\/privat\/apps\/madplan$/, { timeout: 15_000 });
  // API: another «enable» is a no-op
  const again = await page.request.post("/api/backend/privat/addons/madplan/enable", { headers: CSRF });
  expect(again.status()).toBe(200);

  await page.locator("[data-testid=disable-app]:visible").first().click();
  await page.getByTestId("disable-confirm").click();
  await expect(page).toHaveURL(/\/privat\/apps$/, { timeout: 15_000 });
  await expect(page.getByTestId("toast")).toContainText("Madplan");
  await shot(page, info, "X12", "after-disable");
  const off2 = await page.request.post("/api/backend/privat/addons/madplan/disable", { headers: CSRF });
  expect(off2.status()).toBe(200);
  expect((await off2.json()).enabled).toBe(false);

  await page.goto("/privat/apps/madplan");
  await waitIdle(page);
  await page.getByTestId("enable-again").click();
  await page.getByTestId("enable-confirm").click();
  // the kept page turns into the app page as soon as the app is on (the «slået til» sheet goes with it)
  await expect(page.getByRole("button", { name: "Åbn appen" }).or(page.getByTestId("app-page")).first()).toBeVisible({ timeout: 15_000 });
  const rows = ((await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[]).filter((a) => a.key === "madplan");
  expect(rows.map((a) => a.enabled)).toEqual([true]);
});

test("plan-app uden plan: «Prøv gratis» → checkout med appen → prøveperiode og appen er slået til", async ({ page }, info) => {
  await privatUser(page, info, "x12-plan", "Ole Berg");
  const r = await page.request.post("/api/backend/privat/addons/madplan/enable", { headers: CSRF });
  expect(r.status()).toBe(409);
  await page.goto("/privat/butik/madplan");
  await waitIdle(page);
  await page.locator("[data-testid=needs-plan]:visible").first().click();
  await page.getByTestId("plan-go").click();
  await payFakeStripe(page);
  await expect(page).toHaveURL(/\/privat\/apps\/madplan$/, { timeout: 30_000 });
  const apps = (await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[];
  expect(apps.find((a) => a.key === "madplan")!.enabled).toBe(true);
  await shot(page, info, "X12", "plan-app-on");
});
