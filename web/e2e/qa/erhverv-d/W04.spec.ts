import { readFileSync } from "node:fs";
import { expect, test, type FrameLocator } from "@playwright/test";
import { API_LOG, noHorizontalScroll } from "../erhverv-p1a/p1a-helpers";
import { closeAll, EVID, uniquePhone, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W04 – number verification (P0, DB-016): «Code entry, resend cooldown, wrong/expired code, verified and exhausted-attempt
 * state.» A phone number in the widget's «Bliv kontaktet» is stored only after the visitor typed the 6-digit code the
 * business sent to it (simulated SMS: read from the API log). The chat is switched on without any phone number of the
 * business – the SMS goes out with the business's name as sender. */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

/** All simulated codes to `e164`, oldest first. */
const codes = (e164: string) => readFileSync(API_LOG, "utf8").split("\n").filter((l) => l.includes("sms.simulated") && l.includes(e164))
  .map((l) => l.match(/er (\d{6})\./)?.[1]).filter(Boolean) as string[];
async function newCode(e164: string, before: number) {
  await expect.poll(() => codes(e164).length, { timeout: 15_000 }).toBeGreaterThan(before);
  return codes(e164).at(-1)!;
}
const wrong = (code: string) => (code === "000000" ? "111111" : "000000");

async function askToBeCalled(chat: FrameLocator, display: string) {
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = chat.locator("form.contact");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await form.getByLabel("Telefon").fill(display);
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).click();
  return chat.locator(".code-step");
}

test("W04 · kode sendt, nedtælling på «Send ny kode», forkert og ufuldstændig kode, bekræftet → henvendelse med bekræftet nummer", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const phone = uniquePhone();
  const { v, chat, close } = await visitor(browser, page);
  const code = await askToBeCalled(chat, phone.display);
  await expect(code).toBeVisible();
  await expect(code.locator(".hint")).toHaveText(`Vi har sendt en kode på 6 cifre til ${phone.e164.slice(3, 5)} •• •• ${phone.e164.slice(-2)}. Den gælder i 10 minutter.`);
  const resend = code.getByRole("button", { name: /Send ny kode/ });
  await expect(resend).toBeDisabled();
  await expect(resend).toHaveText(/Send ny kode \(\d+ s\)/);
  // nothing is stored before the number is proven
  expect((await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).total).toBe(0);
  const right = await newCode(phone.e164, 0);
  await code.getByLabel("Kode fra SMS").fill("12");
  await code.getByRole("button", { name: "Bekræft" }).click();
  await expect(code.locator(".err")).toHaveText("Skriv de 6 cifre fra SMS'en.");
  await code.getByLabel("Kode fra SMS").fill(wrong(right));
  await code.getByRole("button", { name: "Bekræft" }).click();
  await expect(code.locator(".err")).toHaveText("Koden passer ikke. Du har 4 forsøg tilbage.");
  await v.screenshot({ path: `${EVID("W04")}/${info.project.name}-forkert-kode.png` });
  await code.getByLabel("Kode fra SMS").fill(right);
  await code.getByRole("button", { name: "Bekræft" }).click();
  const ok = chat.locator("li.msg.system-ok").last();
  await expect(ok).toContainText("Tak, Henrik Villumsen!");
  await expect(ok.getByRole("link", { name: "Aflys opringningen eller ret dine valg" })).toHaveAttribute("href", /\/kunde\/[\w-]{40,}$/);
  await expect(ok.getByRole("link")).toHaveAttribute("rel", "noopener noreferrer");
  await v.screenshot({ path: `${EVID("W04")}/${info.project.name}-bekraeftet.png` });
  await noHorizontalScroll(v);
  const lead = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items[0];
  expect([lead.contact_phone, Boolean(lead.phone_verified_at)]).toEqual([phone.display, true]);
  // the owner sees the proven number on the lead
  await page.goto(`/app/leads/${lead.id}`);
  await expect(page.getByText("Nummer bekræftet med SMS-kode")).toBeVisible();
  await close();
});

test("W04 · for mange forsøg: koden låses, «Send ny kode» efter 30 s giver en ny kode, der virker", async ({ page, browser }, info) => {
  test.setTimeout(120_000);
  w = await widgetWorkspace(page, info);
  const phone = uniquePhone();
  const { v, chat, close } = await visitor(browser, page);
  const code = await askToBeCalled(chat, phone.display);
  const first = await newCode(phone.e164, 0);
  const left = ["4", "3", "2", "1"];
  for (const n of left) {
    await code.getByLabel("Kode fra SMS").fill(wrong(first));
    await code.getByRole("button", { name: "Bekræft" }).click();
    await expect(code.locator(".err")).toHaveText(`Koden passer ikke. Du har ${n} forsøg tilbage.`);
  }
  await code.getByLabel("Kode fra SMS").fill(wrong(first));
  await code.getByRole("button", { name: "Bekræft" }).click();
  await expect(code.locator(".err")).toHaveText("Koden passer ikke. Bed om en ny kode.");
  await code.getByLabel("Kode fra SMS").fill(first); // even the right code is refused now
  await code.getByRole("button", { name: "Bekræft" }).click();
  await expect(code.locator(".err")).toHaveText("For mange forsøg. Bed om en ny kode.");
  await v.screenshot({ path: `${EVID("W04")}/${info.project.name}-for-mange-forsoeg.png` });
  // the server's 30 s cooldown since the first code
  const resend = code.getByRole("button", { name: /Send ny kode/ });
  const before = codes(phone.e164).length;
  await resend.click(); // too soon for the server (409 too_soon → the widget counts down), or a new code at once
  await expect(async () => {
    if (codes(phone.e164).length > before) return;
    if (await resend.isEnabled()) await resend.click();
    throw new Error("venter på en ny kode");
  }).toPass({ timeout: 45_000, intervals: [1000] });
  const second = await newCode(phone.e164, before);
  await expect(resend).toBeDisabled(); // a new cooldown
  await code.getByLabel("Kode fra SMS").fill(second);
  await code.getByRole("button", { name: "Bekræft" }).click();
  await expect(chat.locator("li.msg.system-ok").last()).toContainText("Tak, Henrik Villumsen!");
  await close();
});

test("W04 · udløbet kode og «Ret nummer»; kun e-mail kræver ingen kode", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const phone = uniquePhone();
  const { v, chat, close } = await visitor(browser, page);
  // The 10-minute expiry itself is tested against the real clock in tests/qa/test_qa_w04_w09_w13.py; here the widget
  // shows the server's `code_expired` answer (simulated for this one request).
  await v.context().route("**/contact/verify", (route) => route.fulfill({ status: 409, contentType: "application/json",
    body: JSON.stringify({ code: "code_expired", message: "Koden er udløbet. Bed om en ny.", field_errors: [] }) }));
  const code = await askToBeCalled(chat, phone.display);
  await code.getByLabel("Kode fra SMS").fill(await newCode(phone.e164, 0));
  await code.getByRole("button", { name: "Bekræft" }).click();
  await expect(code.locator(".err")).toHaveText("Koden er udløbet. Bed om en ny kode.");
  await expect(code.getByRole("button", { name: "Send ny kode" })).toBeEnabled();
  await v.screenshot({ path: `${EVID("W04")}/${info.project.name}-udloebet.png` });
  await code.getByRole("button", { name: "Ret nummer" }).click();
  const form = chat.locator("form.contact");
  await expect(form).toBeVisible();
  await form.getByLabel("Telefon").fill("");
  await form.getByLabel("E-mail").fill("henrik@example.com");
  await form.getByRole("button", { name: "Send" }).click();
  await expect(chat.locator("li.msg.system-ok").last()).toContainText("Tak, Henrik Villumsen!");
  await expect(code).toBeHidden();
  const lead = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items[0];
  expect([lead.contact_email, lead.contact_phone, lead.phone_verified_at]).toEqual(["henrik@example.com", null, null]);
  await close();
});
