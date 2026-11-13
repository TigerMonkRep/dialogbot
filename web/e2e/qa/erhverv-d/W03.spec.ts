import { expect, test } from "@playwright/test";
import { smsCodeFor } from "../erhverv-p1a/p1a-helpers";
import { closeAll, confirmCode, EVID, uniquePhone, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W03 – callback request: «Name, phone/country, reason and language; explicit callback request and validation.» */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W03 · validering (navn, kontakt, telefon ved tidsrum, samtykke, ugyldigt nummer) og eksplicit opringning bliver lead + opgave", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = chat.locator("form.contact");
  const send = form.getByRole("button", { name: "Send" });
  const err = form.locator(".err");
  await send.click();
  await expect(err).toHaveText("Skriv dit navn.");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await send.click();
  await expect(err).toHaveText("Skriv e-mail eller telefonnummer.");
  await form.getByLabel("E-mail").fill("henrik@example.com");
  await expect(form.getByLabel("Hvornår må vi ringe?").locator("option")).not.toHaveCount(1);
  await form.getByLabel("Hvornår må vi ringe?").selectOption({ index: 2 }); // 0 = ingen præference, 1 = hurtigst muligt, 2 = first real window
  await send.click();
  await expect(err).toHaveText("Skriv dit telefonnummer, så vi kan ringe dig op.");
  await form.getByLabel("Telefon").fill("abc-nummer");
  await send.click();
  await expect(err).toHaveText("Sæt flueben, så virksomheden må kontakte dig.");
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await send.click();
  await expect(err).toHaveText("Tjek e-mail og telefonnummer."); // server 422 on the phone pattern
  // nothing was created by the rejected attempts
  expect((await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).total).toBe(0);
  const phone = uniquePhone();
  await form.getByLabel("Telefon").fill(phone.display);
  const label = await form.getByLabel("Hvornår må vi ringe?").locator("option:checked").textContent();
  await send.click();
  await confirmCode(chat, phone.e164); // W04: the number is proven with the SMS code first
  await expect(chat.getByText("Tak, Henrik Villumsen! Virksomheden kontakter dig hurtigst muligt.")).toBeVisible();
  await v.screenshot({ path: `${EVID("W03")}/${info.project.name}-sendt.png` });
  const leads = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items;
  expect(leads.length).toBe(1);
  expect([leads[0].contact_name, leads[0].contact_phone, leads[0].contact_email]).toEqual(["Henrik Villumsen", phone.display, "henrik@example.com"]);
  expect(leads[0].callback_from).toBeTruthy();
  const tasks = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/tasks`)).json()).items;
  expect(tasks.map((t: { title: string }) => t.title)).toContain(`Ring Henrik Villumsen op – ${label}`);
  await close();
});

test("W03 · dobbeltklik på Send giver ét lead og én opgave", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { chat, close } = await visitor(browser, page);
  // a conversation must exist first so both clicks race on the same one (as when the visitor chatted before)
  await chat.locator("textarea").fill("Hej");
  await chat.locator("textarea").press("Enter");
  await expect(chat.getByText("[fake] svar på: Hej")).toBeVisible();
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = chat.locator("form.contact");
  await form.getByLabel("Navn").fill("Peter Holm");
  const phone = uniquePhone();
  await form.getByLabel("Telefon").fill(phone.display);
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).click();
  // W04: the code step; the double click lands on «Bekræft», which sends the form once
  const code = chat.locator(".code-step");
  await expect(code).toBeVisible();
  await code.getByLabel("Kode fra SMS").fill(await smsCodeFor(phone.e164));
  await code.getByRole("button", { name: "Bekræft" }).dblclick();
  await expect(chat.getByText("Tak, Peter Holm!").first()).toBeVisible();
  await page.waitForTimeout(1000);
  const leads = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items;
  const tasks = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/tasks`)).json()).items;
  expect(leads.length).toBe(1);
  expect(tasks.length).toBe(1);
  await expect(chat.getByText("Tak, Peter Holm!")).toHaveCount(1);
  await close();
});

test("W03 · formularen spørger om årsag (hvad det drejer sig om), så virksomheden ved, hvorfor den skal ringe", async ({ page, browser }, info) => {
  test.fail(true, "F-E2D-03-W03: S2 new – «Bliv kontaktet» spørger ikke om årsagen: formularen har kun navn, e-mail, telefon og tidsrum; …");
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  await v.screenshot({ path: `${EVID("W03")}/${info.project.name}-formular.png` });
  // Requirement W03: «Name, phone/country, reason and language». The frame always sends note: "" (frame.js:107).
  await expect(chat.locator("form.contact").getByLabel(/Hvad drejer det sig om|Årsag|Hvad vil du tale om/)).toBeVisible({ timeout: 5_000 }); // known: fail fast
  await close();
});
