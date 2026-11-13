import { expect, test, type Page } from "@playwright/test";
import { evid, smsLog, noHorizontalScroll, snap, unlock, uniqueIp, uniqueMobile } from "./p1a-helpers";

/* F-AUD26-02-P06 (Fürster 12/11: «A, SMS-kode først»): «Ring mig op nu» on /proev – and the chat widget, which is the
 * same component – rings only a number its visitor proved with a 6-digit SMS code: number → «Vi har sendt en kode til …»
 * → code → «ringer nu». Against the real API with CONNECTORS_PROVIDER=fake and TELEPHONY_PROVIDER=fake: the SMS is
 * only written to the API log (read here, like the Privat/funnel specs do) and the call is only simulated. Needs a
 * configured sales workspace (SALES_WORKSPACE_ID); skipped where GET /demo-call says unavailable (CI without one).
 * Peter rings at once day and night, so the spec is the same at 21:00 as at 10:00 – the run's Copenhagen time is
 * recorded as an annotation. */
const ID = "P06-sms";
evid(ID);
const log = (page: Page) => page.locator("[role=log]").first();

function cphHour() {
  return Number(new Intl.DateTimeFormat("da-DK", { hour: "2-digit", hourCycle: "h23", timeZone: "Europe/Copenhagen" }).format(new Date()));
}

/** The newest simulated SMS to `e164` in the API log (any language: the 6 digits). */
async function smsCode(e164: string, after = 0): Promise<string> {
  let code: string | undefined;
  await expect.poll(() => {
    const lines = smsLog().split("\n").filter((l) => l.includes("sms.simulated") && l.includes(e164));
    code = lines.length > after ? lines.at(-1)?.match(/\b(\d{6})\b/)?.[1] : undefined;
    return code;
  }, { timeout: 15_000 }).toBeTruthy();
  return code!;
}
const smsCount = (e164: string) => smsLog().split("\n").filter((l) => l.includes("sms.simulated") && l.includes(e164)).length;

async function open(page: Page, path: string) {
  await page.setExtraHTTPHeaders({ "x-real-ip": uniqueIp() });
  await unlock(page);
  const info = await (await page.request.get("/api/backend/demo-call", { headers: { "x-requested-with": "dialogbot" } })).json();
  test.skip(!info.available, "Demo-opkald er ikke sat op (SALES_WORKSPACE_ID) – kører på den lokale QA-stak");
  test.info().annotations.push({ type: "kl. (København)", description: `${cphHour()}:xx – ${cphHour() >= 20 || cphHour() < 8 ? "aften/nat" : "dag"}` });
  await page.goto(path);
}

async function toNumberStep(page: Page, call: string, company: string, branch: RegExp) {
  await page.getByRole("button", { name: call }).click();
  await expect(log(page).locator("p")).toHaveCount(3); // Peter asks for the company (after «typing»)
  await page.locator("#chat-input").fill(company);
  await page.locator("#chat-input").press("Enter");
  await page.getByRole("button", { name: branch }).first().click();
  await expect(page.getByRole("checkbox")).toBeVisible();
}

test("P06 · nummer → SMS-kode → forkert kode afvises → rigtig kode → «ringer nu»", async ({ page }, info) => {
  await open(page, "/da/proev");
  const mobile = uniqueMobile();
  const e164 = `+45${mobile}`;
  const display = mobile.replace(/(\d{2})(?=\d)/g, "$1 ");
  await toNumberStep(page, "Ja, ring til mig", "Nørgaard Tømrer", /Håndværk/);
  await page.getByRole("checkbox").check();
  const codePost = page.waitForRequest((r) => r.url().endsWith("/api/backend/demo-call/code") && r.method() === "POST");
  await page.locator("#chat-input").fill(mobile);
  await page.locator("#chat-input").press("Enter");
  expect((await codePost).postDataJSON()).toMatchObject({ consent: true, language: "da" });

  // the code step: clear text, «send igen» only after 30 s, nobody rung yet
  const step = page.locator("[data-code-step]");
  await expect(step).toContainText(`Vi har sendt en kode til ${display}`);
  await expect(log(page)).toContainText(`Vi har sendt en kode til ${display}`);
  await expect(page.locator("[data-resend]")).toBeDisabled();
  await expect(page.locator("[data-resend]")).toContainText(/Send igen om \d+ s/);
  await expect(page.getByLabel("Kode fra SMS")).toHaveAttribute("autocomplete", "one-time-code");
  await expect(log(page)).not.toContainText("Jeg ringer til");
  await noHorizontalScroll(page);
  await snap(page, info, ID, "kode");

  const code = await smsCode(e164);
  await page.getByLabel("Kode fra SMS").fill(code === "000000" ? "111111" : "000000");
  await page.getByLabel("Kode fra SMS").press("Enter");
  await expect(page.locator("#code-hint")).toContainText("Koden passer ikke. Du har 4 forsøg tilbage.");
  await expect(page.getByLabel("Kode fra SMS")).toHaveAttribute("aria-invalid", "true");
  await snap(page, info, ID, "forkert-kode");

  const call = page.waitForRequest((r) => r.url().endsWith("/api/backend/demo-call") && r.method() === "POST");
  await page.getByLabel("Kode fra SMS").fill(code);
  await page.getByLabel("Kode fra SMS").press("Enter");
  const body = (await call).postDataJSON();
  expect(body).toMatchObject({ phone: mobile, company: "Nørgaard Tømrer", consent: true });
  expect(String(body.verification_token)).toHaveLength(43);
  await expect(log(page)).toContainText(`Jeg ringer til ${display} nu`);
  await expect(page.locator("main")).toContainText(`Ringer til ${display}`);
  await expect(page.locator("[data-code-step]")).toHaveCount(0);
  await noHorizontalScroll(page);
  await snap(page, info, ID, "ringer");
});

test("P06 · på engelsk: kodetrin, fejl og «send igen» efter 30 s på sidens sprog", async ({ page }, info) => {
  test.setTimeout(90_000);
  await open(page, "/en/proev");
  const mobile = uniqueMobile();
  const e164 = `+45${mobile}`;
  await toNumberStep(page, "Yes, call me", "Fjord Dental", /Clinic/i);
  await page.getByRole("checkbox").check();
  await page.locator("#chat-input").fill(mobile);
  await page.locator("#chat-input").press("Enter");
  await expect(page.locator("[data-code-step]")).toContainText("We have sent a code to");
  await smsCode(e164);
  const sent = smsCount(e164);
  expect(smsLog()).toContain("Your Dialogbot code is"); // the SMS in the page's language
  await page.getByLabel("Code from SMS").fill("12");
  await page.getByLabel("Code from SMS").press("Enter");
  await expect(page.locator("#code-hint")).toContainText("The code is 6 digits.");
  await expect(page.locator("[data-resend]")).toBeDisabled();
  await expect(page.locator("[data-resend]")).toBeEnabled({ timeout: 35_000 });
  await expect(page.locator("[data-resend]")).toHaveText("Send again");
  await page.locator("[data-resend]").click();
  await expect(log(page)).toContainText("New code sent to");
  await smsCode(e164, sent);
  await expect(page.locator("[data-resend]")).toBeDisabled();
  await snap(page, info, ID, "en-send-igen");
  // «Change number» goes back to the number step without ringing anybody
  await page.getByRole("button", { name: "Change number" }).click();
  await expect(page.getByRole("checkbox")).toBeVisible();
  await expect(log(page)).not.toContainText("I'm calling");
});

test("P06 · chat-widgetten (samme komponent) beder også om koden, før Peter ringer", async ({ page }, info) => {
  await open(page, "/da/byggevejledning");
  // open by default on wide screens, closed on a phone: open it there with the floating launcher
  const call = page.getByRole("button", { name: "Ja, ring til mig" });
  if (!(await call.waitFor({ timeout: 3000 }).then(() => true, () => false))) await page.locator("button[aria-expanded=false]").last().click();
  await expect(call).toBeVisible();
  const mobile = uniqueMobile();
  await toNumberStep(page, "Ja, ring til mig", "Widget ApS", /Klinik/);
  await page.getByRole("checkbox").check();
  await page.locator("#chat-input").fill(mobile);
  await page.locator("#chat-input").press("Enter");
  await expect(page.locator("[data-code-step]")).toContainText("Vi har sendt en kode til");
  const code = await smsCode(`+45${mobile}`);
  await page.getByLabel("Kode fra SMS").fill(code);
  await page.getByLabel("Kode fra SMS").press("Enter");
  await expect(log(page)).toContainText("Jeg ringer til");
  await snap(page, info, ID, "widget-ringer");
});
