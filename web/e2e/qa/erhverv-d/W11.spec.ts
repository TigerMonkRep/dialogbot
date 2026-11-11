import { expect, test } from "@playwright/test";
import { API, closeAll, CSRF, EVID, forwardPublicApi, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W11 – widget/public slot selector: «Date/slots/timezone, loading, no slots, limited availability, stale provider and
 * alternatives.» Stale provider = the connected calendar cannot be read (dev hook POST /dev/fake-calendar/busy-down):
 * decision F-EB-05-BK15 → the booking is made from opening hours and awaits confirmation. */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

async function connectCalendar(page: import("@playwright/test").Page, wsId: string) {
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-e2d-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  // OAuth callback lands on PUBLIC_BASE_URL (:8000 default); forwarded to API_BASE_URL when that differs (d-helpers)
  await forwardPublicApi(page.context(), { maxRedirects: 0 });
  await page.goto(r.authorize_url);
  await expect(page).toHaveURL(/integrationer/);
}

test("W11 · tiderne i widgetten er API'ets ledige tider med dato og klokkeslæt; skift af type henter nye tider", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info, { booking: true });
  await page.request.post(`/api/backend/workspaces/${w.wsId}/bookings/types`, { headers: CSRF, data: { name: "Gulvslibning (heldag)", duration_minutes: 480 } });
  const api = await (await page.request.get(`${API}/api/v1/public/webchat/${w.key}/booking`)).json();
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Book en tid" }).click();
  const form = chat.locator("form.book");
  const starts = form.getByLabel("Tidspunkt");
  expect(await starts.locator("option").allTextContents()).toEqual(api.slots.map((s: { label: string }) => s.label));
  expect(api.slots[0].label).toMatch(/^(mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag) \d+\. \w+ kl\. \d\d\.\d\d$/);
  // the 8-hour type only fits 08–16 or 12–20 within 08–20 opening hours: different, fewer times
  await form.getByLabel("Hvad drejer det sig om?").selectOption({ label: "Gulvslibning (heldag)" });
  await expect.poll(async () => (await starts.locator("option").allTextContents()).join("|")).not.toBe(api.slots.map((s: { label: string }) => s.label).join("|"));
  for (const t of await starts.locator("option").allTextContents()) expect(t).toMatch(/kl\. (08|09|10|11|12)\.\d\d$/);
  await v.screenshot({ path: `${EVID("W11")}/${info.project.name}-tider.png` });
  await close();
});

test("W11 · ingen ledige tider: tydelig tom-tilstand, Book afvises lokalt, og «Annullér» fører tilbage til «Bliv kontaktet»", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info, { booking: true });
  const s = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings/settings`)).json();
  // earliest in 14 days, horizon 1 day: nothing free
  expect((await page.request.put(`/api/backend/workspaces/${w.wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 336, horizon_days: 1, buffer_minutes: 0 } })).ok()).toBeTruthy();
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Book en tid" }).click();
  const form = chat.locator("form.book");
  await expect(form.getByLabel("Tidspunkt").locator("option")).toHaveText(["Ingen ledige tider lige nu"]);
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await form.getByLabel("Telefon").fill("+45 20 30 40 50");
  await form.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
  await form.getByRole("button", { name: "Book", exact: true }).click();
  await expect(form.locator(".err")).toHaveText("Vælg et tidspunkt.");
  await v.screenshot({ path: `${EVID("W11")}/${info.project.name}-ingen-tider.png` });
  await form.getByRole("button", { name: "Annullér" }).click();
  await expect(chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" })).toBeVisible();
  expect((await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings?days=30`)).json()).items.length).toBe(0);
  await close();
});

test("W11 · kalenderen kan ikke læses: tider fra åbningstiden, kunden får «noteret … en medarbejder bekræfter», aftalen afventer", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info, { booking: true });
  await connectCalendar(page, w.wsId);
  expect((await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${w.wsId}&down=true`, { headers: CSRF })).ok()).toBeTruthy();
  try {
    const { v, chat, close } = await visitor(browser, page);
    await chat.getByRole("button", { name: "Book en tid" }).click();
    const form = chat.locator("form.book");
    await expect(form.getByLabel("Tidspunkt").locator("option").first()).not.toHaveText("Ingen ledige tider lige nu");
    const label = (await form.getByLabel("Tidspunkt").locator("option:checked").textContent())!;
    await form.getByLabel("Navn").fill("Henrik Villumsen");
    await form.getByLabel("Telefon").fill("+45 20 30 40 50");
    await form.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
    await form.getByRole("button", { name: "Book", exact: true }).dblclick();
    await expect(chat.getByText(`Tak, Henrik Villumsen! Din tid ${label} er noteret. En medarbejder bekræfter tiden.`)).toBeVisible();
    await expect(chat.getByText(/Du er booket/)).toHaveCount(0);
    await v.screenshot({ path: `${EVID("W11")}/${info.project.name}-afventer.png` });
    await close();
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${w.wsId}&down=false`, { headers: CSRF });
  }
  const items = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings?days=14`)).json()).items;
  expect(items.length).toBe(1); // double click → one booking
  expect([items[0].source, items[0].confirmation, items[0].calendar_event_id]).toEqual(["webchat", "pending", null]);
  const tasks = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/tasks`)).json()).items as { title: string }[];
  expect(tasks.some((t) => t.title.startsWith("Bekræft aftale:"))).toBeTruthy();
});

test("W11 · den besøgende kan nå alle ledige tider i bookinghorisonten (ikke kun de første 24 ≈ 2 dage)", async ({ page, browser }, info) => {
  test.fail(true, "F-E2D-10-W11: S2 new – Widgetten viser kun de første 24 ledige tider (≈ 2 dage ved 08–20 og 60 min); resten af …");
  w = await widgetWorkspace(page, info, { booking: true });
  const s = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings/settings`)).json();
  expect((await page.request.put(`/api/backend/workspaces/${w.wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 0, horizon_days: 14, buffer_minutes: 0 } })).ok()).toBeTruthy();
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Book en tid" }).click();
  const labels = await chat.locator("form.book").getByLabel("Tidspunkt").locator("option").allTextContents();
  await v.screenshot({ path: `${EVID("W11")}/${info.project.name}-horisont.png` });
  // open 08–20 every day, horizon 14 days: a time 7+ days ahead must be choosable (bookings/router.py:264 limit=24)
  const inAWeek = new Date(Date.now() + 8 * 86_400_000);
  const day = `${inAWeek.toLocaleDateString("da-DK", { day: "numeric", timeZone: "Europe/Copenhagen" })} ${inAWeek.toLocaleDateString("da-DK", { month: "long", timeZone: "Europe/Copenhagen" })}`;
  test.info().annotations.push({ type: "offered", description: `${labels.length} tider: ${labels[0]} … ${labels[labels.length - 1]}` });
  expect(labels.some((l) => l.includes(` ${day} `))).toBeTruthy();
  await close();
});

test("W11 · tidszonen står ved tiderne (virksomhedens lokale tid)", async ({ page, browser }, info) => {
  test.fail(true, "F-E2D-05-W11: S3 new – Widgetten oplyser aldrig tidszonen: opringnings-tidsrum («I morgen formiddag (8–12)») og …");
  w = await widgetWorkspace(page, info, { booking: true });
  const { chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Book en tid" }).click();
  // Requirement W11: «Date/slots/timezone». Labels are «tirsdag 10. november kl. 14.00» with no zone anywhere.
  await expect(chat.locator("form.book")).toContainText(/dansk tid|Europe\/Copenhagen|tidszone|lokal tid|CET|CEST/i);
  await close();
});
