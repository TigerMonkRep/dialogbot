import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* QA BK06 + BK15 (e2e-erhverv B): calendar connection is honest (never a green stub), and /app/aftaler tells the
 * truth about the connected calendar and what can be done there. */
const CSRF = { "x-requested-with": "dialogbot" };

async function bookingReady(page: import("@playwright/test").Page, wsId: string) {
  const week = [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], open: "08:00", close: "20:00" }];
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "opening_hours", title: "Åbningstider", content: { weekly: week } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  const typ = await (await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } })).json();
  const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/settings`)).json();
  expect((await page.request.put(`/api/backend/workspaces/${wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 } })).ok()).toBeTruthy();
  return typ.id as string;
}

test("BK06 · integrationer: intet er grønt før autorisation; Google forbundet vises som simuleret", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/settings/integrationer");
  await expect(page.getByText("Testmiljø: forbindelser og handlinger er simulerede", { exact: false })).toBeVisible();
  const google = page.locator('[data-connector="google_calendar"]');
  await expect(google.getByText("Ikke forbundet", { exact: true })).toBeVisible();
  // «På vej»/Zapier entries carry no connect button and no green status
  await expect(page.locator("li:not([data-connector])").getByRole("button", { name: "Forbind" })).toHaveCount(0);
  for (const key of ["google_calendar", "microsoft_calendar", "twilio_sms", "webhook", "zapier", "make"]) {
    const card = page.locator(`[data-connector="${key}"]`);
    if (await card.count()) await expect(card.getByText(/^Forbundet/)).toHaveCount(0);
  }
  expect(await page.locator("body").innerText()).not.toMatch(/staging/i);
  await google.getByRole("button", { name: "Forbind" }).click();
  await expect(page.getByText("Google Kalender er forbundet.")).toBeVisible();
  await expect(page.locator('[data-connector="google_calendar"]').getByText("Forbundet (simuleret)")).toBeVisible();
  await page.screenshot({ path: `../qa/evidence/BK06/${info.project.name}-google-simuleret.png`, fullPage: true });
});

test("BK15 · /app/aftaler: kalenderkortet viser den forbundne Google-kalender (ikke «Ikke forbundet»)", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await bookingReady(page, wsId);
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-eb-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await page.goto(r.authorize_url); // fake OAuth: the callback verifies and redirects back to the app
  await expect(page).toHaveURL(/integrationer/);
  const g = (await (await page.request.get(`/api/backend/workspaces/${wsId}/integrations`)).json()).items.find((x: { key: string }) => x.key === "google_calendar");
  expect(g.status).toBe("connected");
  await page.goto("/app/aftaler");
  const card = page.locator("aside").getByText("Kalender", { exact: true }).locator("..");
  await page.screenshot({ path: `../qa/evidence/BK15/${info.project.name}-aftaler-kalenderkort.png`, fullPage: true });
  await expect(card.getByText("Ikke forbundet", { exact: true })).toHaveCount(0);
  await expect(card.getByText(/Uden kalender kender Dialogbot kun åbningstiderne/)).toHaveCount(0);
});

async function bookedCard(page: Page, info: TestInfo) {
  const { wsId } = await freshOwner(page, info);
  const typeId = await bookingReady(page, wsId);
  const slots = (await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/slots?type_id=${typeId}`)).json()).items;
  const b = await (await page.request.post(`/api/backend/workspaces/${wsId}/bookings`, { headers: CSRF, data: { type_id: typeId, start: slots[0].start, name: "Mette Jensen", phone: "+4520304050" } })).json();
  const day = new Date(b.starts_at).toLocaleDateString("sv-SE", { timeZone: "Europe/Copenhagen" });
  await page.goto(`/app/aftaler?uge=${day}`);
  await page.getByRole("button", { name: /Mette Jensen/ }).click();
  await expect(page.getByRole("button", { name: "Aflys" })).toBeVisible();
}

test("BK15 · /app/aftaler lover kun «Flyt», hvis en aftale kan flyttes (F-EB-07)", async ({ page }, info) => {
  await bookedCard(page, info);
  await page.screenshot({ path: `../qa/evidence/BK15/${info.project.name}-aftalekort.png`, fullPage: true });
  const promisesMove = await page.getByText(/Flyt eller aflys her/).count();
  const canMove = await page.getByRole("button", { name: /Flyt/ }).count();
  expect(promisesMove === 0 || canMove > 0, `promises «Flyt» (${promisesMove}) without a move button (${canMove})`).toBeTruthy();
});

test("BK15 · en aftale kan flyttes i /app/aftaler", async ({ page }, info) => {
  test.fail(true, "BK15 move appointment in /app/aftaler: not-implemented");
  await bookedCard(page, info);
  await expect(page.getByRole("button", { name: /Flyt/ })).toBeVisible({ timeout: 3000 });
});
