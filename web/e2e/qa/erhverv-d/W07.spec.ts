import { expect, test } from "@playwright/test";
import { closeAll, confirmCode, EVID, uniquePhone, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W07 – customer confirmation: «Summary of agreed details, optional receipt destination and edit-before-submit.»
 * Not built: «Send» submits straight away and only «Tak, <navn>!» is shown. This spec documents the gap. */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W07 · opsummering af det aftalte med «Ret» før afsendelse, og valgfri kvittering", async ({ page, browser }, info) => {
  test.fail(true, "W07: not-implemented – opsummering med «Ret» og valgfri kvittering");
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = chat.locator("form.contact");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  const phone = uniquePhone();
  await form.getByLabel("Telefon").fill(phone.display);
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).click();
  await confirmCode(chat, phone.e164); // W04
  await v.screenshot({ path: `${EVID("W07")}/${info.project.name}-ingen-opsummering.png` });
  // what actually happens: the lead is created at once, no summary step
  await expect(chat.getByText("Tak, Henrik Villumsen! Virksomheden kontakter dig hurtigst muligt.")).toBeVisible();
  const leads = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items;
  expect(leads.length).toBe(1);
  // requirement: a summary with edit-before-submit and an optional receipt destination
  await expect(chat.getByRole("button", { name: /Ret|Rediger/ })).toBeVisible({ timeout: 3000 });
  await expect(chat.getByLabel(/kvittering/i)).toBeVisible({ timeout: 3000 });
  await close();
});
