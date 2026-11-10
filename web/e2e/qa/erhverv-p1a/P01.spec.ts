import { expect, test } from "@playwright/test";
import { evid, internalLinksOk, noHorizontalScroll, sectionsWithSeveralPrimaries, snap, unlock } from "./p1a-helpers";

/* QA P01 (e2e-erhverv A, wave 2): / – full landing page, responsive navigation, product demonstration, reception and
 * campaign entry points. Implementation: «/» is the entry page (two doors, web/src/app/(public)/page.tsx); the business
 * landing moved to /erhverv (docs/site-pages.md). Both are checked here; the /erhverv details are X02. */
const ID = "P01";
evid(ID);

test.beforeEach(async ({ page }) => { await unlock(page); });

test("P01 · indgangen: sprog-omdirigering, én h1, demo, døre til Erhverv/Privat, ingen døde links", async ({ page }, info) => {
  const r = await page.goto("/");
  expect(r?.status()).toBe(200);
  await expect(page).toHaveURL(/\/da$/);
  await expect(page.locator("h1")).toHaveCount(1);
  // product demonstration: the call mock and the «Prøv den» entry
  await expect(page.getByText("Tømrer Hansen, du taler med Dialogbot.").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Prøv den – den ringer til dig/ }).first()).toHaveAttribute("href", "/da/proev");
  // reception door → /erhverv ; private door → /privat
  await expect(page.getByRole("link", { name: /Til virksomheder/ })).toHaveAttribute("href", "/da/erhverv");
  await expect(page.getByRole("link", { name: /Til dig derhjemme/ })).toHaveAttribute("href", "/privat");
  await noHorizontalScroll(page);
  expect(await internalLinksOk(page)).toEqual([]);
  await snap(page, info, ID, "indgang");
});

test("P01 · responsiv navigation: fuld menu på desktop, menu-knap på mobil, ankre virker", async ({ page }, info) => {
  await page.goto("/da");
  const mobile = (page.viewportSize()?.width ?? 0) < 1024;
  if (mobile) {
    const menu = page.locator("summary[aria-label]").first();
    await expect(menu).toBeVisible();
    await menu.click();
    await snap(page, info, ID, "mobilmenu");
    const priser = page.locator("details[open]").getByRole("link", { name: "Priser" });
    await expect(priser).toBeVisible();
    await priser.click();
  } else {
    await page.getByRole("navigation").first().getByRole("link", { name: "Priser" }).click();
  }
  await expect(page).toHaveURL(/#priser$/);
  await expect(page.locator("#priser")).toBeInViewport();
  await expect(page.getByRole("link", { name: "Log ind" }).first()).toHaveAttribute("href", "/login");
});

test("P01 · indgange til reception og kampagner fra Erhverv-landingen", async ({ page }) => {
  await page.goto("/da/erhverv");
  // reception: try / funnel / build guide
  await expect(page.locator("a[href='/start']").first()).toBeVisible();
  await expect(page.locator("a[href='/da/byggevejledning']").first()).toBeVisible();
  // campaigns: a visible entry point
  const kampagne = page.getByRole("link", { name: "Planlæg en kampagne" });
  await expect(kampagne).toBeVisible();
  await kampagne.click();
  await expect(page).toHaveURL(/\/da\/kontakt$/);
});

test("P01 · én primær knap pr. sektion på indgangen", async ({ page }) => {
  await page.goto("/da");
  expect(await sectionsWithSeveralPrimaries(page)).toEqual([]);
});

test("P01 · husket dør: efter /erhverv sender «/» direkte dertil; ?aud=reset viser indgangen igen", async ({ page }) => {
  await page.goto("/da/erhverv");
  await page.goto("/");
  await expect(page).toHaveURL(/\/da\/erhverv$/);
  await page.goto("/?aud=reset");
  await expect(page).toHaveURL(/\/da\?aud=reset$|\/da$/);
  await expect(page.getByRole("link", { name: /Til virksomheder/ })).toBeVisible();
});
