import { expect, test } from "@playwright/test";
import { evid, internalLinksOk, snap, unlock } from "./p1a-helpers";

/* QA P08 (e2e-erhverv A, wave 2): /contact – sales/support contact form, validation, submission confirmation and failure
 * state; DB-006 no unsupported claims. Implementation: /kontakt (web/src/app/kontakt/page.tsx) is a static page with phone,
 * e-mail and address – no form. The CTAs «Planlæg en kampagne» and «Book opsætning» on /erhverv lead here. */
const ID = "P08";
evid(ID);

test("P08 · /kontakt: telefon, e-mail og adresse er korrekte links; ingen døde links", async ({ page }, info) => {
  expect((await page.goto("/da/kontakt"))?.status()).toBe(200);
  await expect(page.locator("main a[href='tel:+4593703433']").first()).toBeVisible();
  await expect(page.locator("main a[href='mailto:info@dialogbot.dk']").first()).toBeVisible();
  await expect(page.locator("main")).toContainText("CVR-nr. 25632710");
  expect(await internalLinksOk(page)).toEqual([]);
  await snap(page, info, ID, "kontakt");
});

test("P08 · CTA'erne «Planlæg en kampagne» og «Book opsætning» lander på en side, der kan bruges", async ({ page }) => {
  await unlock(page);
  for (const name of ["Planlæg en kampagne", "Book opsætning"]) {
    await page.goto("/da/erhverv");
    await page.getByRole("link", { name }).click();
    await expect(page).toHaveURL(/\/da\/kontakt$/);
    await expect(page.locator("main a[href^='mailto:']").first()).toBeVisible();
  }
});

test("P08 · kontaktformular med validering, kvittering og fejltilstand (krav) – ikke bygget", async ({ page }) => {
  test.info().annotations.push({ type: "not-implemented", description: "/kontakt har ingen formular." });
  await page.goto("/da/kontakt");
  await expect(page.locator("main form")).toHaveCount(0);
});
