import { expect, test, type Page } from "@playwright/test";
import { unlock } from "../erhverv-p1a/p1a-helpers";
import { noHorizontalScroll, shot } from "./p2-helpers";

/** X06 (P1): Privat-landing tydeligt anderledes end Erhverv (orange), samme logo, header-vælger Erhverv/Privat der virker
 *  og husker valget (cookie db_aud; "/" sender til den valgte dør; "/?aud=reset" viser indgangen igen). Public pages only
 *  – no backend needed beyond Next. /, /erhverv and /signup sit behind the preview gate (PREVIEW_GATE=on on CI): unlock
 *  first, like the other public-page specs. */

async function logo(page: Page) {
  // the mark in the header: same shape (radius 28 %, white speech bubble path), colour from --color-accent
  const mark = page.locator("header").first().locator("svg path").first();
  const box = mark.locator("xpath=ancestor::span[1]");
  return {
    path: await mark.getAttribute("d"),
    radius: await box.evaluate((el) => { const s = getComputedStyle(el); return Math.round(parseFloat(s.borderTopLeftRadius) / parseFloat(s.width) * 100); }),
    bg: await box.evaluate((el) => getComputedStyle(el).backgroundColor),
    word: (await page.locator("header").first().getByText("Dialogbot", { exact: true }).first().evaluate((el) => {
      const s = getComputedStyle(el); return `${s.fontFamily}|${s.fontWeight}`;
    })),
  };
}

test("Privat er orange, Erhverv er blå; logoet har samme form og ordmærke", async ({ page }, info) => {
  await page.goto("/privat");
  await expect(page.locator("[data-theme=privat]").first()).toBeVisible();
  const privat = await logo(page);
  const cta = await page.getByRole("link", { name: "Prøv gratis i 14 dage" }).first().evaluate((el) => getComputedStyle(el).backgroundColor);
  await noHorizontalScroll(page);
  await shot(page, info, "X06", "privat");

  await unlock(page);
  await page.goto("/da/erhverv");
  await expect(page.locator("[data-theme=privat]")).toHaveCount(0);
  const erhverv = await logo(page);
  await shot(page, info, "X06", "erhverv");

  expect(privat.path).toBe(erhverv.path);
  expect(privat.radius).toBe(erhverv.radius);
  expect(privat.word).toBe(erhverv.word);
  expect(privat.bg).toBe("rgb(196, 70, 26)");   // #C4461A (privat accent, AA contrast)
  expect(erhverv.bg).toBe("rgb(36, 86, 246)");  // #2456F6 Klods-blå
  expect(cta).toBe("rgb(196, 70, 26)");
});

test("vælgeren i headeren: Privat aktiv på /privat, Erhverv aktiv på /erhverv, og valget huskes på /", async ({ page }) => {
  await page.context().clearCookies();
  await unlock(page);
  await page.goto("/?aud=reset");
  await expect(page).not.toHaveURL(/\/privat$|\/erhverv$/);

  await page.goto("/privat");
  const nav = page.getByRole("navigation", { name: "Vælg: virksomhed eller privat" }).first();
  await expect(nav).toBeVisible();
  await expect(nav.locator("[aria-current=page]")).toHaveText(/Privat/);
  expect((await page.context().cookies()).find((c) => c.name === "db_aud")?.value).toBe("privat");
  await page.goto("/");
  await expect(page).toHaveURL(/\/privat$/);

  // click the other door
  await page.getByRole("navigation", { name: "Vælg: virksomhed eller privat" }).first().getByRole("link", { name: /Erhverv/ }).click();
  await expect(page).toHaveURL(/\/erhverv$/);
  const nav2 = page.getByRole("navigation", { name: "Vælg: virksomhed eller privat" }).first();
  await expect(nav2.locator("[aria-current=page]")).toHaveText(/Erhverv/);
  await expect.poll(async () => (await page.context().cookies()).find((c) => c.name === "db_aud")?.value).toBe("erhverv");
  await page.goto("/");
  await expect(page).toHaveURL(/\/erhverv$/);

  // and back to Privat by a client-side click (AudienceMemory sets the cookie)
  await nav2.getByRole("link", { name: /Privat/ }).click();
  await expect(page).toHaveURL(/\/privat$/);
  await expect.poll(async () => (await page.context().cookies()).find((c) => c.name === "db_aud")?.value).toBe("privat");
  await page.reload();
  await page.goto("/");
  await expect(page).toHaveURL(/\/privat$/);

  // reset shows the entry page again
  await page.goto("/?aud=reset");
  await expect(page).not.toHaveURL(/\/privat$|\/erhverv$/);
  expect((await page.context().cookies()).find((c) => c.name === "db_aud")).toBeUndefined();
});

test("«Prøv gratis i 14 dage» går til checkout-vejen (signup → konto?plan=plus)", async ({ page }) => {
  await page.context().clearCookies();
  await unlock(page);
  await page.goto("/privat");
  const href = await page.getByRole("link", { name: "Prøv gratis i 14 dage" }).first().getAttribute("href");
  expect(href).toBe("/privat/konto?plan=plus&interval=month");
  await page.getByRole("link", { name: "Prøv gratis i 14 dage" }).first().click();
  await expect(page).toHaveURL(/\/signup\?next=.*plan%3Dplus/, { timeout: 15_000 });
});
