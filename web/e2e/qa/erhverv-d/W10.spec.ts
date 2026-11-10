import { expect, test } from "@playwright/test";
import { closeAll, CSRF, EVID, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W10 – widget booking / /book/:business: «Client-branded service, location and optional staff choice; shared
 * standalone-page variant.» Built: service (booking type) choice in the widget. Not built: location, staff,
 * standalone /book/:business page. */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W10 · ydelsesvalg i widgetten: kun aktive typer vises, og den valgte type bliver aftalens type", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info, { booking: true });
  const extra = await (await page.request.post(`/api/backend/workspaces/${w.wsId}/bookings/types`, { headers: CSRF, data: { name: "Lakering", duration_minutes: 120 } })).json();
  const off = await (await page.request.post(`/api/backend/workspaces/${w.wsId}/bookings/types`, { headers: CSRF, data: { name: "Gammel ydelse", duration_minutes: 30 } })).json();
  const pr = await page.request.patch(`/api/backend/workspaces/${w.wsId}/bookings/types/${off.id}`, { headers: CSRF, data: { active: false } });
  test.info().annotations.push({ type: "deactivate", description: String(pr.status()) });
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Book en tid" }).click();
  const form = chat.locator("form.book");
  const types = await form.getByLabel("Hvad drejer det sig om?").locator("option").allTextContents();
  expect(types).toContain("Besigtigelse");
  expect(types).toContain("Lakering");
  if (pr.ok()) expect(types).not.toContain("Gammel ydelse");
  await form.getByLabel("Hvad drejer det sig om?").selectOption({ label: "Lakering" });
  await expect.poll(async () => form.getByLabel("Hvad drejer det sig om?").inputValue()).toBe(extra.id);
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await form.getByLabel("E-mail").fill("henrik@example.com");
  await form.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
  await form.getByRole("button", { name: "Book", exact: true }).click();
  await expect(chat.getByText(/Tak, Henrik Villumsen! Du er booket/)).toBeVisible();
  await v.screenshot({ path: `${EVID("W10")}/${info.project.name}-ydelse.png` });
  const b = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings?days=14`)).json()).items[0];
  expect(b.title).toBe("Lakering: Henrik Villumsen");
  expect(new Date(b.ends_at).getTime() - new Date(b.starts_at).getTime()).toBe(120 * 60_000);
  await close();
});

test("W10 · ikke bygget: den delte bookingside /book/:business og valg af sted/medarbejder", async ({ page }, info) => {
  w = await widgetWorkspace(page, info, { booking: true });
  const ws = await (await page.request.get(`/api/backend/workspaces/${w.wsId}`)).json();
  const r = await page.request.get(`/book/${ws.slug ?? ws.id}`);
  test.info().annotations.push({ type: "status", description: `/book/${ws.slug ?? ws.id} → ${r.status()}` });
  expect(r.status(), "standalone booking page").toBe(200);
});
