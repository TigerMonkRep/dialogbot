import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* BK15 – decision 2026-11-10 (F-EB-05-BK15): when the connected calendar's busy time cannot be read, a booking is
 * still made from opening hours but marked «Afventer bekræftelse»; the owner confirms it on /app/aftaler and it is
 * then written to the calendar. The outage is simulated per workspace (dev hook, fake connectors only). */
const CSRF = { "x-requested-with": "dialogbot" };

test("BK15 · kalenderen kan ikke læses: aftalen afventer bekræftelse, ejeren bekræfter, og den skrives i kalenderen", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const week = [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], open: "08:00", close: "20:00" }];
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "opening_hours", title: "Åbningstider", content: { weekly: week } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  const typ = await (await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } })).json();
  const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/settings`)).json();
  expect((await page.request.put(`/api/backend/workspaces/${wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 } })).ok()).toBeTruthy();
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-bk15p-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await page.goto(r.authorize_url);
  await expect(page).toHaveURL(/integrationer/);

  // Google's free/busy is down: «Book for en kunde» still offers times, the result says «afventer bekræftelse»
  expect((await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=true`, { headers: CSRF })).ok()).toBeTruthy();
  try {
    await page.goto("/app/aftaler");
    await page.getByLabel("Navn").fill("Mette Jensen");
    await page.getByRole("button", { name: "Book", exact: true }).click();
    await expect(page.getByText(/afventer bekræftelse, fordi kalenderen ikke kunne læses/)).toBeVisible();
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=false`, { headers: CSRF });
  }
  const b = (await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings?days=14`)).json()).items[0];
  expect([b.confirmation, b.calendar_event_id]).toEqual(["pending", null]);

  // the week shows the label and the count; the owner confirms once the calendar answers again
  const day = new Date(b.starts_at).toLocaleDateString("sv-SE", { timeZone: "Europe/Copenhagen" });
  await page.goto(`/app/aftaler?uge=${day}`);
  await expect(page.getByText(/1 aftaler afventer bekræftelse/)).toBeVisible();
  const card = page.getByRole("button", { name: /Mette Jensen/ });
  await expect(card.getByText("Afventer bekræftelse", { exact: true })).toBeVisible();
  await card.click();
  await expect(page.getByText(/Kalenderen kunne ikke læses, da tiden blev booket/)).toBeVisible();
  await page.screenshot({ path: `../qa/evidence/BK15/${info.project.name}-afventer-bekraeftelse.png`, fullPage: true });
  await page.getByRole("button", { name: "Bekræft", exact: true }).click();
  await expect(page.getByRole("button", { name: /Mette Jensen/ }).getByText("Afventer bekræftelse", { exact: true })).toHaveCount(0);
  const after = (await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings?days=14`)).json()).items[0];
  expect([after.confirmation, after.calendar_sync]).toEqual(["confirmed", "synced"]);
  expect(after.calendar_event_id).toBeTruthy();
  await page.screenshot({ path: `../qa/evidence/BK15/${info.project.name}-bekraeftet.png`, fullPage: true });
});
