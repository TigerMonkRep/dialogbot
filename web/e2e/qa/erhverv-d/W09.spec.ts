import { expect, test, type Page } from "@playwright/test";
import { noHorizontalScroll } from "../erhverv-p1a/p1a-helpers";
import { closeAll, confirmCode, EVID, uniquePhone, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W09 – customer preferences (P0, DB-016): «Secure callback cancellation and communication-preference/opt-out views with
 * invalid-link state.» After «Bliv kontaktet» the widget gives the customer a secure link (/kunde/<token>): see the
 * call back, cancel it, and say «ring ikke til mig i kampagner» (the business's do-not-call list). */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

async function requestCallback(page: Page, browser: import("@playwright/test").Browser, info: import("@playwright/test").TestInfo) {
  w = await widgetWorkspace(page, info);
  const phone = uniquePhone();
  const vis = await visitor(browser, page);
  await vis.chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = vis.chat.locator("form.contact");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await form.getByLabel("Telefon").fill(phone.display);
  await form.getByLabel("Hvornår må vi ringe?").selectOption({ index: 2 });
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).click();
  await confirmCode(vis.chat, phone.e164);
  const link = vis.chat.getByRole("link", { name: "Aflys opringningen eller ret dine valg" });
  const href = (await link.getAttribute("href"))!;
  return { ...vis, phone, href, path: new URL(href).pathname };
}

test("W09 · kunden ser opringningen, frabeder sig kampagneopkald og aflyser – ejeren ser det på henvendelsen", async ({ page, browser }, info) => {
  const { v, chat, close, phone, path } = await requestCallback(page, browser, info);
  // the link opens in a new tab from the chat
  const [tab] = await Promise.all([v.context().waitForEvent("page"), chat.getByRole("link", { name: "Aflys opringningen eller ret dine valg" }).click()]);
  await tab.waitForLoadState();
  expect(new URL(tab.url()).pathname).toBe(path);
  await expect(tab.getByRole("heading", { level: 1 })).toHaveText(/^Din henvendelse til E2E /);
  await expect(tab.getByText("Hej Henrik.")).toBeVisible();
  await expect(tab.getByText(`ringer dig op på ${phone.e164.slice(3, 5)} •• •• ${phone.e164.slice(-2)}.`, { exact: false })).toBeVisible();
  await expect(tab.getByText("Nummeret er bekræftet med SMS-kode.")).toBeVisible();
  await expect(tab.getByText(/^Tidsrum: .+–\d{2}[.:]\d{2} \(.+\)\.$/)).toBeVisible();
  await expect(tab.getByText(/Siden vises af Dialogbot på vegne af E2E /)).toBeVisible();
  await tab.screenshot({ path: `${EVID("W09")}/${info.project.name}-oversigt.png`, fullPage: true });
  await noHorizontalScroll(tab);
  // preference: no campaign calls
  const box = tab.getByLabel(/Ring ikke til mig i kampagner fra/);
  await expect(box).not.toBeChecked();
  await box.check();
  await tab.getByRole("button", { name: "Gem mine valg" }).click();
  await expect(tab.getByText("Dine valg er gemt.")).toBeVisible();
  await tab.reload();
  await expect(tab.getByLabel(/Ring ikke til mig i kampagner fra/)).toBeChecked();
  // cancel the call back (with a confirm step)
  await tab.getByRole("button", { name: "Aflys opringningen" }).click();
  await expect(tab.getByText("Vil du aflyse opringningen? Virksomheden ringer så ikke.")).toBeVisible();
  await tab.getByRole("button", { name: "Ja, aflys" }).click();
  await expect(tab.getByText("Opringningen er aflyst. Virksomheden ringer ikke.")).toBeVisible();
  await expect(tab.getByRole("button", { name: "Aflys opringningen" })).toHaveCount(0);
  await tab.screenshot({ path: `${EVID("W09")}/${info.project.name}-aflyst.png`, fullPage: true });
  // the owner: lead marked, its call task closed
  const lead = (await (await page.request.get(`/api/backend/workspaces/${w!.wsId}/leads`)).json()).items[0];
  expect(Boolean(lead.callback_cancelled_at)).toBe(true);
  const tasks = (await (await page.request.get(`/api/backend/workspaces/${w!.wsId}/tasks?status=open`)).json()).items as { lead_id: string; status: string }[];
  expect(tasks.filter((t) => t.lead_id === lead.id && t.status === "open")).toHaveLength(0);
  await page.goto(`/app/leads/${lead.id}`);
  await expect(page.getByText("Kunden har aflyst opringningen")).toBeVisible();
  await page.screenshot({ path: `${EVID("W09")}/${info.project.name}-ejer.png` });
  await close();
});

test("W09 · ugyldigt, erstattet og andet formåls link viser «Linket virker ikke» – på alle 8 sprog", async ({ page, browser }, info) => {
  const { v, chat, close, path, phone } = await requestCallback(page, browser, info);
  // a new request in the same conversation (after a reload) gives a new link; the old one stops working. The number is
  // already proven in this conversation, so no new code.
  await v.reload();
  await v.getByRole("button", { name: "Åbn chat" }).click();
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = chat.locator("form.contact");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await form.getByLabel("Telefon").fill(phone.display);
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).click();
  const again = chat.getByRole("link", { name: "Aflys opringningen eller ret dine valg" });
  await expect(again).toBeVisible();
  await expect(chat.locator(".code-step")).toBeHidden();
  const newest = new URL((await again.getAttribute("href"))!).pathname;
  expect(newest).not.toBe(path);
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Linket virker ikke");
  await expect(page.getByText("Brug det nyeste link, du har fået i chatten, eller kontakt virksomheden direkte.")).toBeVisible();
  await page.screenshot({ path: `${EVID("W09")}/${info.project.name}-ugyldigt.png` });
  await page.goto(newest);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Din henvendelse til/);
  // a callback token on the booking door is not a booking link
  await page.goto(newest.replace("/kunde/", "/booking/manage/"));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Linket virker ikke");
  const titles: Record<string, string> = { da: "Linket virker ikke", en: "This link does not work", de: "Dieser Link funktioniert nicht",
    es: "Este enlace no funciona", fr: "Ce lien ne fonctionne pas", it: "Questo link non funziona", no: "Lenken virker ikke", sv: "Länken fungerar inte" };
  const base = new URL(page.url()).origin;
  for (const [lang, title] of Object.entries(titles)) {
    await page.context().addCookies([{ name: "dlg_lang", value: lang, url: base }]);
    await page.goto("/kunde/ukendt-link");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
  }
  await page.context().addCookies([{ name: "dlg_lang", value: "da", url: base }]);
  await close();
});
