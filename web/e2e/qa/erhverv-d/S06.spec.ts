import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { EVID } from "./d-helpers";

/* S06 – /app/settings/notifications: «Owner alerts, channels, preferences and links to report recipients.»
 * Not built as a page. What exists: push on/off in Konto and the weekly report mail on /app/ugen. */
test("S06 · notifikationsindstillinger: siden findes med kanaler og link til rapportmodtagere", async ({ page }, info) => {
  test.fail(true, "S06: not-implemented – notifikationsindstillinger /app/settings/notifications");
  await freshOwner(page, info);
  const r = await page.request.get("/app/settings/notifications", { maxRedirects: 5 });
  test.info().annotations.push({ type: "status", description: `/app/settings/notifications → ${r.status()}` });
  await page.goto("/app/konto");
  await page.screenshot({ path: `${EVID("S06")}/${info.project.name}-konto.png`, fullPage: true });
  expect(r.status()).toBe(200);
});
