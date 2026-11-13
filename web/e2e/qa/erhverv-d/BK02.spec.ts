import { expect, test } from "@playwright/test";
import { login, SEEDED } from "../../helpers";
import { closeAll, confirmCode, CSRF, EVID, forwardPublicApi, uniquePhone, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* BK02 – /app/bookings/:bookingId: «Booking detail, linked conversation/enquiry, provider, timeline, sync,
 * notification state and permitted actions.» Built as an expandable card on /app/aftaler (no own route). */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

let phone = uniquePhone();
async function pendingWidgetBooking(page: import("@playwright/test").Page, browser: import("@playwright/test").Browser, info: import("@playwright/test").TestInfo) {
  w = await widgetWorkspace(page, info, { booking: true });
  const r = await (await page.request.post(`/api/backend/workspaces/${w.wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-e2d-bk02-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await forwardPublicApi(page.context(), { maxRedirects: 0 });
  await page.goto(r.authorize_url);
  await expect(page).toHaveURL(/integrationer/);
  await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${w.wsId}&down=true`, { headers: CSRF });
  try {
    const { chat, close } = await visitor(browser, page);
    await chat.locator("textarea").fill("Jeg vil gerne have en besigtigelse");
    await chat.locator("textarea").press("Enter");
    await expect(chat.getByText("[fake] svar på: Jeg vil gerne have en besigtigelse")).toBeVisible();
    await chat.getByRole("button", { name: "Book en tid" }).click();
    const form = chat.locator("form.book");
    await form.getByLabel("Navn").fill("Henrik Villumsen");
    phone = uniquePhone(); // W04 on the booking door (F-VER1113-04): a fresh number, the code limit is per number
    await form.getByLabel("Telefon").fill(phone.display);
    await form.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
    await form.getByRole("button", { name: "Book", exact: true }).click();
    await confirmCode(chat, phone.e164);
    await expect(chat.getByText(/er noteret\. En medarbejder bekræfter tiden\./)).toBeVisible();
    await close();
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${w.wsId}&down=false`, { headers: CSRF });
  }
  return (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/bookings?days=14`)).json()).items[0];
}

test("BK02 · aftalekortet: kilde, kontakt, «Afventer bekræftelse», udbyder, link til samtale og henvendelse; Bekræft skriver i kalenderen", async ({ page, browser }, info) => {
  test.setTimeout(120_000);
  const b = await pendingWidgetBooking(page, browser, info);
  expect([b.source, b.confirmation]).toEqual(["webchat", "pending"]);
  expect(b.conversation_id).toBeTruthy();
  expect(b.lead_id).toBeTruthy();
  const day = new Date(b.starts_at).toLocaleDateString("sv-SE", { timeZone: "Europe/Copenhagen" });
  await page.goto(`/app/aftaler?uge=${day}`);
  await expect(page.getByText(/Google/).first()).toBeVisible(); // provider named in the calendar box
  const card = page.getByRole("button", { name: /Henrik Villumsen/ });
  await expect(card.getByText("Afventer bekræftelse", { exact: true })).toBeVisible();
  await card.click();
  await expect(page.getByText(`${b.label} · Webchat`)).toBeVisible();
  await expect(page.getByText(phone.display).first()).toBeVisible();
  await page.screenshot({ path: `${EVID("BK02")}/${info.project.name}-detalje.png`, fullPage: true });
  // linked conversation and enquiry open and show this customer
  const conv = page.getByRole("link", { name: "Samtalen" });
  await expect(conv).toHaveAttribute("href", `/app/opkald/${b.conversation_id}`);
  await expect(page.getByRole("link", { name: "Henvendelse" })).toHaveAttribute("href", `/app/opkald/henvendelser/${b.lead_id}`);
  const convPage = await page.context().newPage();
  const cr = await convPage.goto(`/app/opkald/${b.conversation_id}`);
  expect(cr?.status()).toBe(200);
  await expect(convPage.getByText("Jeg vil gerne have en besigtigelse").first()).toBeVisible();
  const lr = await convPage.goto(`/app/opkald/henvendelser/${b.lead_id}`);
  expect(lr?.status()).toBe(200);
  await expect(convPage.getByText("Henrik Villumsen").first()).toBeVisible();
  await convPage.close();
  // permitted action: confirm (calendar answers again) → written to the calendar, label gone; survives reload
  await page.getByRole("button", { name: "Bekræft", exact: true }).click();
  await expect(page.getByRole("button", { name: /Henrik Villumsen/ }).getByText("Afventer bekræftelse", { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: /Henrik Villumsen/ }).getByText("Afventer bekræftelse", { exact: true })).toHaveCount(0);
  const after = (await (await page.request.get(`/api/backend/workspaces/${w!.wsId}/bookings?days=14`)).json()).items[0];
  expect([after.confirmation, after.calendar_sync]).toEqual(["confirmed", "synced"]);
});

test("BK02 · aftalen har sin egen adresse (/app/bookings/:id), så push, mail og opgaver kan linke direkte til den", async ({ page, browser }, info) => {
  test.fail(true, "F-E2D-11-BK02: S3 new – En aftale har ingen egen side: /app/bookings/:id giver 404 (kun /app/bookings → /app/aftaler …");
  test.setTimeout(120_000);
  const b = await pendingWidgetBooking(page, browser, info);
  const r = await page.request.get(`/app/bookings/${b.id}`, { maxRedirects: 5 });
  test.info().annotations.push({ type: "status", description: `/app/bookings/${b.id} → ${r.status()} ${r.url()}` });
  expect(r.status()).toBe(200);
});

test("BK02 · roller: læser ser ikke aftaler og kan ikke aflyse via API'et", async ({ page }) => {
  await login(page, SEEDED.reader);
  await page.goto("/app/aftaler");
  await expect(page.getByText("Aftaler kan ses af medarbejdere, administratorer og ejere.")).toBeVisible();
  const ws = await (await page.request.get("/api/auth/workspace").catch(() => null))?.json().catch(() => null);
  const me = await (await page.request.get("/api/backend/workspaces")).json();
  const wsId = (ws?.workspace_id ?? (me.items ?? me)[0].id) as string;
  const list = await page.request.get(`/api/backend/workspaces/${wsId}/bookings?days=14`);
  expect(list.status()).toBe(403);
  const cancel = await page.request.post(`/api/backend/workspaces/${wsId}/bookings/00000000-0000-0000-0000-000000000001/cancel`, { headers: CSRF, data: {} });
  expect(cancel.status()).toBe(403);
});
