import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { PREVIEW_CODE, SEEDED, login } from "./helpers";

/* Fürster 12/11: «Travelpayouts skal kun være på Privat» + «når jeg åbner appen i en browser, åbner Travelpayouts en ny
 * fane med rejsetilbud». Root cause: the Travelpayouts «Drive» site script (emrldtp.cc) sat on /erhverv – where "/" sends
 * every returning Erhverv visitor – and its monetisation module hooks every click on the page and opens travel offers
 * in a new tab (window.open(url, "_blank"): «overtab»/«undertab»/«delayed_redirect»). Guard: no page may load a
 * Travelpayouts script, and no page may open a tab, popup or redirect itself when the visitor clicks around. On Privat,
 * Travelpayouts lives only in the booking links (with the marker) the person clicks themselves.
 *
 * Runs in the journeys job (real stack, preview gate on) and in the privat job (NEXT_PUBLIC_PRIVAT_FAKE=1). The
 * Travelpayouts hosts are blocked here, so the test does not depend on their servers: the request alone fails it. */

const TP_HOST = /(^|\.)(emrldtp\.cc|travelpayouts\.com|tp\.media|tp\.st|aviasales\.[a-z]+|tp[okxm]\.(li|lu|lv|mx|ro|gr|lt))$/i;
const fake = process.env.NEXT_PUBLIC_PRIVAT_FAKE === "1";

async function guard(context: BrowserContext) {
  const tp: string[] = [];
  const popups: string[] = [];
  await context.route(/.*/, (route) => {
    const url = route.request().url();
    let host = "";
    try { host = new URL(url).hostname; } catch { /* data:, blob: */ }
    if (TP_HOST.test(host)) { tp.push(url); return route.abort(); }
    return route.fallback();
  });
  context.on("page", (p) => popups.push(p.url() || "about:blank"));
  return { tp, popups };
}

/** Clicks on plain text (never a link or a button): Drive's popunder fires on any click anywhere on the page. */
async function clickAround(page: Page) {
  const before = page.url();
  for (const sel of ["h1", "main p", "footer"]) {
    const el = page.locator(sel).first();
    if (await el.count()) await el.click({ position: { x: 2, y: 2 }, force: true, noWaitAfter: true }).catch(() => {});
    await page.waitForTimeout(300);
  }
  await page.mouse.click(5, 300);
  await page.waitForTimeout(1500);
  expect(page.url(), "siden sendte sig selv videre efter et klik").toBe(before);
}

async function unlockPreview(page: Page) {
  // The preview gate is on in the journeys job only; in the fake build there is nothing to unlock.
  await page.request.post("/api/preview/unlock", { headers: { "x-requested-with": "dialogbot" }, data: { code: PREVIEW_CODE, next: "/" } }).catch(() => null);
}

const ERHVERV = ["/da", "/da/erhverv", "/da/priser", "/start/1", "/da/privatliv", "/da/vilkaar", "/login"];
const PRIVAT = ["/privat", "/privat/start/1"];

test.describe("ingen Travelpayouts-script, ingen nye faner", () => {
  for (const path of ERHVERV) {
    test(`Erhverv ${path}: intet Travelpayouts, ingen popup`, async ({ page, context }) => {
      const { tp, popups } = await guard(context);
      await unlockPreview(page);
      const r = await page.goto(path);
      expect(r?.status(), path).toBeLessThan(400);
      await clickAround(page);
      expect(tp, "requests til Travelpayouts").toEqual([]);
      expect(popups, "nye faner/popups").toEqual([]);
      expect(await page.locator("script[src*='emrldtp'], script#travelpayouts-drive").count()).toBe(0);
    });
  }

  test("forsiden med husket Erhverv-dør («åbner appen i en browser»): intet Travelpayouts, ingen popup", async ({ page, context, baseURL }) => {
    test.skip(fake, "fake-buildet har preview-låsen uden koder (privat-jobbet); journeys-jobbet dækker den");
    const { tp, popups } = await guard(context);
    await unlockPreview(page);
    await context.addCookies([{ name: "db_aud", value: "erhverv", url: baseURL ?? "http://localhost:3000" }]);
    await page.goto("/");
    await expect(page).toHaveURL(/\/erhverv/);
    await clickAround(page);
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });

  test("Erhverv-appen /app (logget ind): intet Travelpayouts, ingen popup", async ({ page, context }) => {
    test.skip(fake, "kræver backend (journeys-jobbet)");
    const { tp, popups } = await guard(context);
    await login(page, SEEDED.owner);
    await page.goto("/app");
    await clickAround(page);
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });

  for (const path of PRIVAT) {
    test(`Privat ${path}: intet globalt Travelpayouts-script, ingen popup`, async ({ page, context }) => {
      const { tp, popups } = await guard(context);
      const r = await page.goto(path);
      expect(r?.status(), path).toBeLessThan(400);
      await clickAround(page);
      expect(tp).toEqual([]);
      expect(popups).toEqual([]);
    });
  }

  test("Privat-appen (Min dag, Butikken): intet Travelpayouts-script, ingen popup", async ({ page, context }) => {
    test.skip(!fake, "kræver et web-build med NEXT_PUBLIC_PRIVAT_FAKE=1");
    const { tp, popups } = await guard(context);
    await page.addInitScript(() => sessionStorage.setItem("dialogbot-privat-fake-login", "1"));
    for (const path of ["/privat/dag", "/privat/butik"]) {
      await page.goto(path);
      await clickAround(page);
    }
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });
});
