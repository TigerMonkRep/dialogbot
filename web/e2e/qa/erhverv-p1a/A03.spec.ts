import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { DEMO_PASSWORD, latestMailLink } from "../../helpers";
import { CSRF, evid, expireTokens, mailbox, snap } from "./p1a-helpers";

/* QA A03 (e2e-erhverv A, wave 2): /verify-email – pending verification, resend, verified and expired-link states.
 * Source: web/src/app/verify-email/page.tsx, app/modules/identity/service.py (issue_verification, verify_email, _consume),
 * app/modules/identity/router.py:134-147. */
const ID = "A03";
evid(ID);
const mail = (tag: string, info: TestInfo) => `e2a-a03-${tag}-${info.project.name}-${Date.now()}@example.com`;

async function register(page: Page, email: string) {
  const r = await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: "QA Bekræft", signup_intent: "reception" } });
  expect(r.status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
}
const verifyMails = async (page: Page) => (await mailbox(page)).filter((m) => /verify-email\?token=/.test(m.body_text)).length;

test("A03 · afventer → send nyt link → bekræftet; tilstanden overlever genindlæsning", async ({ page }, info) => {
  const email = mail("happy", info);
  await register(page, email);
  await page.goto("/verify-email");
  await expect(page.getByRole("heading", { name: "Bekræft din e-mail" })).toBeVisible();
  await expect(page.getByText(/Vi har sendt et bekræftelseslink/)).toBeVisible();
  await snap(page, info, ID, "afventer");
  const before = await (async () => { await latestMailLink(page.request, /token=[\w-]+/); return verifyMails(page); })();
  // resend, also with a double click: at most one new mail per click that the UI acknowledges
  await page.getByRole("button", { name: "Send nyt link" }).dblclick();
  await expect(page.getByText("Et nyt link er sendt.")).toBeVisible();
  await expect.poll(() => verifyMails(page), { timeout: 20_000 }).toBeGreaterThan(before);
  await page.waitForTimeout(2000);
  expect(await verifyMails(page), "dobbeltklik må ikke sende to mails").toBe(before + 1);
  // the newest link verifies
  const link = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  await page.goto(link.slice(link.indexOf("/verify-email")));
  await expect(page.getByText("Din e-mail er bekræftet.")).toBeVisible();
  expect((await (await page.request.get("/api/backend/auth/me")).json()).email_verified).toBe(true);
  await snap(page, info, ID, "bekraeftet");
  await page.getByRole("link", { name: /Fortsæt til arbejdsrum/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/1|\/onboarding/);
  // The banner in the app is gone for a verified user
  await page.goto("/app");
  await expect(page.getByRole("link", { name: /bekræft/i })).toHaveCount(0);
});

test("A03 · udløbet link: klar besked og «Send nyt link» virker; brugt link afvises", async ({ page }, info) => {
  const email = mail("udloebet", info);
  await register(page, email);
  const link = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  expect(expireTokens(email, "verify_email")).toMatch(/UPDATE [1-9]/);
  await page.goto(link.slice(link.indexOf("/verify-email")));
  await expect(page.getByText("Linket er udløbet. Bestil et nyt nedenfor.")).toBeVisible();
  await snap(page, info, ID, "udloebet");
  expect((await (await page.request.get("/api/backend/auth/me")).json()).email_verified).toBe(false);
  const n = await verifyMails(page);
  await page.getByRole("button", { name: "Send nyt link" }).click();
  await expect(page.getByText("Et nyt link er sendt.")).toBeVisible();
  await expect.poll(() => verifyMails(page), { timeout: 20_000 }).toBeGreaterThan(n);
  const fresh = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  expect(fresh).not.toBe(link);
  await page.goto(fresh.slice(fresh.indexOf("/verify-email")));
  await expect(page.getByText("Din e-mail er bekræftet.")).toBeVisible();
  // the same link again: refused, not «bekræftet» twice and no crash
  await page.goto(fresh.slice(fresh.indexOf("/verify-email")));
  await expect(page.getByText(/ugyldigt eller allerede brugt/)).toBeVisible();
});

test("A03 · linket åbnet på en anden enhed (ikke logget ind): bekræfter uden login", async ({ page, browser }, info) => {
  const email = mail("enhed", info);
  await register(page, email);
  const link = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  const phone = await browser.newPage();
  await phone.goto(`http://localhost:3200${link.slice(link.indexOf("/verify-email"))}`);
  await expect(phone.getByText("Din e-mail er bekræftet.")).toBeVisible();
  await phone.close();
  expect((await (await page.request.get("/api/backend/auth/me")).json()).email_verified).toBe(true);
});

test("A03 · udløbet link på en anden enhed: «Send nyt link» må ikke sige «Din session er udløbet»", async ({ page, browser }, info) => {
  const email = mail("enhed-udloebet", info);
  await register(page, email);
  const link = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  expireTokens(email, "verify_email");
  const phone = await browser.newPage();
  await phone.goto(`http://localhost:3200${link.slice(link.indexOf("/verify-email"))}`);
  await expect(phone.getByText("Linket er udløbet. Bestil et nyt nedenfor.")).toBeVisible();
  await phone.getByRole("button", { name: "Send nyt link" }).click();
  await phone.waitForTimeout(2500);
  await phone.screenshot({ path: `../qa/evidence/${ID}/${info.project.name}-anden-enhed-send-nyt.png`, fullPage: true });
  // This visitor never had a session here – telling them it «expired» is wrong (F-E2A-06).
  await expect(phone.getByText("Din session er udløbet. Log ind igen for at fortsætte.")).toHaveCount(0);
  await phone.close();
});

test("A03 · serverfejl ved bekræftelse vises som fejl, ikke som «bekræftet»", async ({ page }, info) => {
  const email = mail("500", info);
  await register(page, email);
  await page.route("**/api/backend/auth/verify-email", (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal_error", message: "Der skete en fejl hos os. Prøv igen." }) }));
  await page.goto("/verify-email?token=whatever-token");
  await expect(page.getByText("Der skete en fejl hos os. Prøv igen.")).toBeVisible();
  await expect(page.getByText("Din e-mail er bekræftet.")).toHaveCount(0);
  await snap(page, info, ID, "serverfejl");
});

test("A03 · ingen udviklertekst i kundens afventer-tilstand", async ({ page }, info) => {
  await register(page, mail("tekst", info));
  await page.goto("/verify-email");
  await expect(page.getByText(/Vi har sendt et bekræftelseslink/)).toBeVisible();
  // «I udviklingsmiljøet findes mailen i den simulerede postkasse.» is the same string in production (F-E2A-05).
  await expect(page.getByText(/udviklingsmiljøet|simulerede postkasse/)).toHaveCount(0);
});
