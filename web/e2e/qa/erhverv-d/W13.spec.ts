import { expect, test, type Browser, type Page, type TestInfo } from "@playwright/test";
import { noHorizontalScroll, smsCodeFor } from "../erhverv-p1a/p1a-helpers";
import { CSRF, closeAll, EVID, uniquePhone, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W13 – /booking/manage/:token (P0, DB-007/DB-011/DB-016): «Secure appointment management, verification where needed,
 * reschedule/cancel, policy restrictions and invalid/expired links.» A booking made in the widget comes with a secure
 * link. A booking with a phone number needs an SMS code to that number before it can be moved or cancelled; one with
 * only an e-mail is managed with the link. Changes stop at the business's lead time before the start. */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

async function book(page: Page, browser: Browser, info: TestInfo, contact: { phone?: string; email?: string }) {
  w = await widgetWorkspace(page, info, { booking: true });
  const vis = await visitor(browser, page);
  await vis.chat.getByRole("button", { name: "Book en tid" }).click();
  const form = vis.chat.locator("form.book");
  await expect(form.getByLabel("Tidspunkt").locator("option").first()).not.toHaveText("Ingen ledige tider lige nu");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  if (contact.phone) await form.getByLabel("Telefon").fill(contact.phone);
  if (contact.email) await form.getByLabel("E-mail").fill(contact.email);
  await form.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
  await form.getByRole("button", { name: "Book", exact: true }).click();
  const link = vis.chat.getByRole("link", { name: "Se, flyt eller aflys din tid" });
  await expect(link).toHaveAttribute("href", /\/booking\/manage\/[\w-]{40,}$/);
  return { ...vis, path: new URL((await link.getAttribute("href"))!).pathname };
}
const bookings = async (page: Page) =>
  (await (await page.request.get(`/api/backend/workspaces/${w!.wsId}/bookings?days=30&include_cancelled=true`)).json()).items as { starts_at: string; status: string }[];

test("W13 · kode til aftalens nummer før ændring, flyt til ny tid, aflys – ejeren ser det", async ({ page, browser }, info) => {
  const phone = uniquePhone();
  const { close, path } = await book(page, browser, info, { phone: phone.display });
  const before = (await bookings(page))[0].starts_at;
  const c = await browser.newContext({ viewport: page.viewportSize() ?? undefined, locale: "da-DK", timezoneId: "Europe/Copenhagen" });
  const tab = await c.newPage();
  await tab.goto(path);
  await expect(tab.getByRole("heading", { level: 1 })).toHaveText(/^Din tid hos E2E /);
  await expect(tab.getByText("Besigtigelse")).toBeVisible();
  await expect(tab.getByTestId("booking-status")).toHaveText("Bekræftet");
  await expect(tab.getByText(/^Tiderne er i /)).toBeVisible();
  // verification where needed: the booking has a phone number
  await expect(tab.getByRole("heading", { name: "Bekræft, at det er dig" })).toBeVisible();
  await expect(tab.getByRole("button", { name: "Flyt tiden" })).toHaveCount(0);
  await expect(tab.getByText(`Før du kan flytte eller aflyse, sender vi en kode på 6 cifre til ${phone.e164.slice(3, 5)} •• •• ${phone.e164.slice(-2)}.`)).toBeVisible();
  await tab.screenshot({ path: `${EVID("W13")}/${info.project.name}-kode.png`, fullPage: true });
  await noHorizontalScroll(tab);
  await tab.getByRole("button", { name: "Send kode" }).click();
  await expect(tab.getByRole("button", { name: /Send ny kode \(\d+ s\)/ })).toBeDisabled();
  await tab.getByLabel("Kode fra SMS").fill("123");
  await tab.getByRole("button", { name: "Bekræft" }).click();
  await expect(tab.getByText("Skriv de 6 cifre fra SMS'en.")).toBeVisible();
  const right = await smsCodeFor(phone.e164);
  await tab.getByLabel("Kode fra SMS").fill(right === "000000" ? "111111" : "000000");
  await tab.getByRole("button", { name: "Bekræft" }).click();
  await expect(tab.getByText("Koden passer ikke. Du har 4 forsøg tilbage.")).toBeVisible();
  await tab.getByLabel("Kode fra SMS").fill(right);
  await tab.getByRole("button", { name: "Bekræft" }).click();
  await expect(tab.getByText("Nummeret er bekræftet.")).toBeVisible();
  // move
  await tab.getByRole("button", { name: "Flyt tiden" }).click();
  const select = tab.getByLabel("Ny tid");
  await expect(select.locator("option").first()).toBeAttached();
  await select.selectOption({ index: 2 });
  const chosen = (await select.locator("option:checked").textContent())!;
  await tab.getByRole("button", { name: "Flyt til den valgte tid" }).click();
  await expect(tab.getByText(`Din tid er flyttet til ${chosen}.`)).toBeVisible();
  await expect(tab.getByTestId("booking-when")).toHaveText(chosen);
  await tab.screenshot({ path: `${EVID("W13")}/${info.project.name}-flyttet.png`, fullPage: true });
  const moved = (await bookings(page))[0];
  expect(moved.starts_at).not.toBe(before);
  // cancel
  await tab.getByRole("button", { name: "Aflys tiden" }).click();
  await expect(tab.getByText(`Vil du aflyse tiden ${chosen}?`)).toBeVisible();
  await tab.getByRole("button", { name: "Ja, aflys tiden" }).click();
  await expect(tab.getByText("Din tid er aflyst.")).toBeVisible();
  await expect(tab.getByTestId("booking-status")).toHaveText("Aflyst");
  await expect(tab.getByRole("button", { name: "Flyt tiden" })).toHaveCount(0);
  await tab.screenshot({ path: `${EVID("W13")}/${info.project.name}-aflyst.png`, fullPage: true });
  expect((await bookings(page))[0].status).toBe("cancelled");
  const tasks = (await (await page.request.get(`/api/backend/workspaces/${w!.wsId}/tasks`)).json()).items as { title: string }[];
  expect(tasks.some((t) => /flyttede besigtigelse til .* \(via link\)/.test(t.title))).toBeTruthy();
  expect(tasks.some((t) => /aflyste besigtigelse .* \(via link\)/.test(t.title))).toBeTruthy();
  await c.close();
  await close();
});

test("W13 · kun e-mail: ingen kode; inden for virksomhedens frist kan tiden ikke ændres", async ({ page, browser }, info) => {
  const { close, path } = await book(page, browser, info, { email: "henrik@example.com" });
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Bekræft, at det er dig" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Flyt tiden" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Aflys tiden" })).toBeVisible();
  // the business changes its lead time to a week: the booking is now inside it
  const s = await (await page.request.get(`/api/backend/workspaces/${w!.wsId}/bookings/settings`)).json();
  expect((await page.request.put(`/api/backend/workspaces/${w!.wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 168, horizon_days: 7, buffer_minutes: 0 } })).ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByText(/^Tiden kan ikke ændres her mindre end 168 timer før\. Kontakt E2E /)).toBeVisible();
  await expect(page.getByRole("button", { name: "Flyt tiden" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Aflys tiden" })).toHaveCount(0);
  await page.screenshot({ path: `${EVID("W13")}/${info.project.name}-frist.png`, fullPage: true });
  expect((await bookings(page))[0].status).toBe("confirmed");
  await close();
});

test("W13 · ugyldigt link og et henvendelses-link på booking-døren: «Linket virker ikke»", async ({ page }, info) => {
  await page.goto("/booking/manage/findes-ikke");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Linket virker ikke");
  await expect(page.getByText("Brug det nyeste link, du har fået i chatten, eller kontakt virksomheden direkte.")).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await page.screenshot({ path: `${EVID("W13")}/${info.project.name}-ugyldigt.png` });
  await noHorizontalScroll(page);
});
