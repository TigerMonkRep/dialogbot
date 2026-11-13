import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { noHorizontalScroll } from "../erhverv-p1a/p1a-helpers";

/* M03 (Fürster 13/11): when Dialogbot pauses a workspace, its people see a clear banner in the app – in their own
 * language – that says what waits and that inbound calls and the chat go on. The operator's internal reason is not
 * shown. Resuming removes the banner. */
const EVID = "../qa/evidence/M03";
const CSRF = { "x-requested-with": "dialogbot" };

test("M03 · banner i appen, når arbejdsrummet er sat på pause – også på engelsk – og væk efter genoptagelse", async ({ page }, info) => {
  const owner = await freshOwner(page, info);
  await page.goto("/app");
  await expect(page.locator("[data-suspended-banner]")).toHaveCount(0);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  const base = `/api/backend/operator/admin/operations/workspaces/${owner.wsId}`;
  expect((await page.request.post(`${base}/suspend`, { headers: CSRF, data: { reason: "E2E INTERN: Twilio-hændelse" } })).ok()).toBeTruthy();
  await page.goto("/app");
  const banner = page.locator("[data-suspended-banner]");
  await expect(banner).toContainText("Dialogbot har midlertidigt sat dette arbejdsrum på pause.");
  await expect(banner).toContainText("Indgående opkald og chatten bliver besvaret som normalt.");
  await expect(banner).not.toContainText("INTERN");
  await expect(banner.getByRole("link", { name: "Skriv til support" })).toHaveAttribute("href", "/app/support");
  await noHorizontalScroll(page);
  await page.screenshot({ path: `${EVID}/${info.project.name}-banner.png` });
  // the user's own language (cookie dlg_lang, like the rest of the app)
  await page.context().addCookies([{ name: "dlg_lang", value: "en", url: new URL(page.url()).origin }]);
  await page.goto("/app");
  await expect(banner).toContainText("Dialogbot has temporarily paused this workspace.");
  await expect(banner.getByRole("link", { name: "Contact support" })).toBeVisible();
  await page.context().addCookies([{ name: "dlg_lang", value: "da", url: new URL(page.url()).origin }]);
  expect((await page.request.post(`${base}/resume`, { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app");
  await expect(page.locator("[data-suspended-banner]")).toHaveCount(0);
});
