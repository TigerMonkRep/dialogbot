import { expect, test } from "@playwright/test";
import { evid, internalLinksOk, noHorizontalScroll, snap } from "./p1a-helpers";

/* QA P07 (e2e-erhverv A, wave 2): /help and /help/:article – searchable help centre, categories, readable article
 * template; installation and campaign examples. Implementation: /viden (guides, 2 groups) + /viden/<slug>; /help is 404.
 * No search and no campaign example exist → the scenario is partly not built. */
const ID = "P07";
evid(ID);
const ARTICLES = ["hvad-er-en-ai-receptionist", "ai-telefonsvarer-eller-telefonpasning", "viderestil-telefonen",
  "dialogbot-vs-vocalis", "dialogbot-vs-almindelig-chatbot"];

test("P07 · oversigten har grupper og links til alle artikler; ingen døde links", async ({ page }, info) => {
  expect((await page.goto("/da/viden"))?.status()).toBe(200);
  await expect(page.locator("main h2", { hasText: "Guides" })).toBeVisible();
  await expect(page.locator("main h2", { hasText: "AI-receptionist til din branche" })).toBeVisible();
  for (const a of ARTICLES) await expect(page.locator(`main a[href='/da/viden/${a}']`).first()).toBeAttached();
  expect(await internalLinksOk(page)).toEqual([]);
  await snap(page, info, ID, "viden");
});

test("P07 · artikelskabelon: én h1, brødkrumme tilbage til Viden, læsbar linjelængde, ingen vandret scroll", async ({ page }) => {
  test.fail(true, "F-E2A-09-P07: S2 new – Vandret scroll på mobil (390 px): tre /viden-artikler (206 px) og de juridiske sider (5 px).");
  for (const a of ARTICLES) {
    expect((await page.goto(`/da/viden/${a}`))?.status(), a).toBe(200);
    await expect(page.locator("h1"), a).toHaveCount(1);
    await expect(page.locator("main a[href='/da/viden']").first(), a).toBeAttached();
    const widest = await page.$$eval("main p", (ps) => Math.max(...ps.filter((p) => (p.textContent ?? "").length > 200).map((p) => p.getBoundingClientRect().width).concat(0)));
    expect(widest, `${a}: linjelængde`).toBeLessThanOrEqual(820);
    await noHorizontalScroll(page);
  }
  // installation example
  await page.goto("/da/viden/viderestil-telefonen");
  await expect(page.locator("main")).toContainText("**67*");
});

test("P07 · søgning og kampagneeksempel (krav) – ikke bygget", async ({ page }) => {
  test.info().annotations.push({ type: "not-implemented", description: "/viden har ingen søgning og ingen kampagne-guide; /help findes ikke." });
  await page.goto("/da/viden");
  await expect(page.locator("main input[type=search], main [role=search]")).toHaveCount(0);
  expect((await page.request.get("/help")).status()).toBe(404);
});
