import { expect, test } from "@playwright/test";
import { closeAll, EVID, visitor, widgetWorkspace, type Widget } from "./d-helpers";

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
  await form.getByLabel("Telefon").fill("+45 20 30 40 50");
  const label = await form.getByLabel("Hvornår må vi ringe?").locator("option:checked").textContent();
  await send.click();
  await expect(chat.getByText("Tak, Henrik Villumsen! Virksomheden kontakter dig hurtigst muligt.")).toBeVisible();
  await v.screenshot({ path: `${EVID("W03")}/${info.project.name}-sendt.png` });
  const leads = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items;
  expect(leads.length).toBe(1);
  expect([leads[0].contact_name, leads[0].contact_phone, leads[0].contact_email]).toEqual(["Henrik Villumsen", "+45 20 30 40 50", "henrik@example.com"]);
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
  await form.getByLabel("Telefon").fill("+45 31 32 33 34");
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).dblclick();
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
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  await v.screenshot({ path: `${EVID("W03")}/${info.project.name}-formular.png` });
  // Requirement W03: «Name, phone/country, reason and language». The frame always sends note: "" (frame.js:107).
  await expect(chat.locator("form.contact").getByLabel(/Hvad drejer det sig om|Årsag|Hvad vil du tale om/)).toBeVisible();
  await close();
});
