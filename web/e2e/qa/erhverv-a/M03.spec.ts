import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";

/* QA M03 (e2e-erhverv A): /admin/operations (→ /app/operator/admin/drift) – job/delivery/call/booking-sync status,
 * dependency incidents, controlled retry, suspension; no duplicate calls/bookings. DB-007: no timer-simulated recovery. */
const EVID = "../qa/evidence/M03";
const CSRF = { "x-requested-with": "dialogbot" };

test("M03 · kunden ser ikke drift; operatøren ser database, kø, fejlede opgaver og mails – ingen simuleret genopretning", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  await page.goto("/app/operator/admin/drift");
  await expect(page.getByText("Admin er kun for Dialogbot-operatører.")).toBeVisible();
  expect((await page.request.get("/api/backend/operator/admin/operations")).status()).toBe(403);
  await page.context().clearCookies();

  await freshOwner(page, info);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin/drift");
  for (const h of ["Database og kode", "Opgavekø (7 dage)", "Fejlede opgaver", "Seneste e-mails", "Logbog (seneste 40)"]) {
    await expect(page.getByRole("heading", { name: h })).toBeVisible();
  }
  await expect(page.getByText("Samme version")).toBeVisible();
  // DB-007: nothing on the page changes by itself (no timer-driven "recovered" state)
  const before = await page.locator("main").innerText();
  await page.waitForTimeout(4000);
  expect(await page.locator("main").innerText()).toBe(before);
  await page.screenshot({ path: `${EVID}/${info.project.name}-drift.png`, fullPage: true });
  // M03 asks for call / booking-sync status, dependency incidents, controlled retry and suspension
  const text = before.toLowerCase();
  const missing = [["opkald", /opkald/], ["booking/kalender-synk", /synk|kalender|booking/], ["genkør/prøv igen", /genkør|prøv igen|retry/], ["suspendering", /suspend|pause/]]
    .filter(([, re]) => !(re as RegExp).test(text)).map(([n]) => n);
  info.annotations.push({ type: "missing", description: missing.join(", ") });
  expect(missing, "not implemented on the operations screen").toEqual([]);
});
