import { expect, test } from "@playwright/test";
import { evid, internalLinksOk, noHorizontalScroll, sectionsWithSeveralPrimaries, snap, unlock } from "./p1a-helpers";

/* QA X02 (e2e-erhverv A, wave 2): /erhverv – hero, demo, priser fra … ekskl. moms, CTA til /proev og signup; accentlag;
 * én primær knap pr. sektion. Source: web/src/app/(public)/erhverv/page.tsx, components/mark.tsx, docs/brand.md,
 * docs/site-pages.md («Accentlag»). Price LEVEL is not asserted (the price model changes on another branch); only that
 * a monthly price ex. VAT is shown. */
const ID = "X02";
evid(ID);

test.beforeEach(async ({ page }) => { await unlock(page); });

test("X02 · hero, demo, pris ekskl. moms og CTA'er; ingen døde links; ingen vandret scroll", async ({ page }, info) => {
  const r = await page.goto("/da/erhverv");
  expect(r?.status()).toBe(200);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator("h1")).toContainText("Dialogbot tager telefonen");
  const hero = page.locator("main section").first();
  await expect(hero).toContainText(/\d[\d.]* kr\.\/md\. ekskl\. moms/);
  await expect(hero.locator("a[href='/da/proev']").first()).toBeVisible();
  await expect(hero.locator("a[href='/start']").first()).toBeVisible(); // the signup funnel
  // demo: the example call transcript
  await expect(page.getByText("OPKALD · TØMRERFIRMA (EKSEMPEL)")).toBeVisible();
  // signup reachable from the page
  await expect(page.locator("a[href='/signup']").first()).toBeAttached();
  await noHorizontalScroll(page);
  expect(await internalLinksOk(page)).toEqual([]);
  await snap(page, info, ID, "erhverv");
});

test("X02 · accentlag: gul markør højst én pr. skærmbillede; aldrig på knapper/brødtekst", async ({ page }) => {
  await page.goto("/da/erhverv");
  const marks = await page.$$eval(".mk", (els) => els.map((e) => {
    const r = e.getBoundingClientRect();
    return { kind: Array.from(e.classList).find((c) => /^mk-(marker|underline|ring)$/.test(c)), top: r.top + window.scrollY,
      color: (e as HTMLElement).style.getPropertyValue("--mk-c"), inButton: !!e.closest("a,button,input,footer"),
      inHeading: !!e.closest("h1,h2,h3") || !!e.closest(".font-display") }; // headings and big display figures
  }));
  expect(marks.length).toBeGreaterThan(0);
  expect(marks.filter((m) => m.inButton), "markering på knap/link/footer").toEqual([]);
  expect(marks.filter((m) => !m.inHeading), "markering uden for overskrift").toEqual([]);
  const yellow = marks.filter((m) => m.kind === "mk-marker").map((m) => m.top).sort((a, b) => a - b);
  const vh = page.viewportSize()!.height;
  for (let i = 1; i < yellow.length; i++) expect(yellow[i] - yellow[i - 1], "to gule markører i samme skærmbillede").toBeGreaterThan(vh);
  const lines = marks.filter((m) => m.kind === "mk-underline");
  for (const l of lines) expect(l.color.toUpperCase(), "tynd streg = blæk på Erhverv").toBe("#14213D");
});

test("X02 · én primær knap pr. sektion", async ({ page }, info) => {
  await page.goto("/da/erhverv");
  const bad = await sectionsWithSeveralPrimaries(page);
  if (bad.length) {
    const sec = page.locator("main section", { hasText: "Ét abonnement. Ingen pris pr. henvendelse." }).first();
    await sec.screenshot({ path: `../qa/evidence/${ID}/${info.project.name}-flere-primaere.png` });
  }
  expect(bad).toEqual([]);
});

test("X02 · /erhverv uden sprog sendes til /da/erhverv og husker døren", async ({ page }) => {
  await page.goto("/erhverv");
  await expect(page).toHaveURL(/\/da\/erhverv$/);
  expect((await page.context().cookies()).find((c) => c.name === "db_aud")?.value).toBe("erhverv");
});
