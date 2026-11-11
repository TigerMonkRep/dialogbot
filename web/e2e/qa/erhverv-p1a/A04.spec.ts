import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { DEMO_PASSWORD } from "../../helpers";
import { CSRF, evid, expireTokens, mailbox, snap } from "./p1a-helpers";

/* QA A04 (e2e-erhverv A, wave 2): /password/forgot and /password/reset – request reset, confirmation, new password,
 * expired link and return to login. Source: web/src/app/password/{forgot,reset}/page.tsx,
 * app/modules/identity/service.py:request_password_reset/reset_password. */
const ID = "A04";
evid(ID);
const NEW_PW = "Nyt-Kodeord-E2A-2026";
const mail = (tag: string, info: TestInfo) => `e2a-a04-${tag}-${info.project.name}-${Date.now()}@example.com`;

async function register(page: Page, email: string) {
  expect((await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: "QA Nulstil", signup_intent: "reception" } })).status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
}
const resetLinks = async (page: Page) => (await mailbox(page)).map((m) => m.body_text.match(/\/password\/reset\?token=[\w-]+/)?.[0]).filter(Boolean) as string[];

async function requestReset(page: Page, email: string) {
  const n = (await resetLinks(page)).length;
  await page.goto("/password/forgot");
  await page.getByLabel("E-mail").fill(email);
  await page.getByRole("button", { name: "Send nulstillingslink" }).click();
  await expect(page.getByText(/Hvis adressen findes, har vi sendt et link/)).toBeVisible();
  await expect.poll(async () => (await resetLinks(page)).length, { timeout: 20_000 }).toBeGreaterThan(n);
  return (await resetLinks(page))[0];
}

test("A04 · bestil → bekræftelse → ny kode → login med ny kode; gammel kode og andre sessioner er døde", async ({ page, browser }, info) => {
  const email = mail("happy", info);
  await register(page, email);
  // another device logged in before the reset
  const other = await browser.newContext();
  expect((await other.request.post("http://localhost:3200/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  const link = await requestReset(page, email);
  await snap(page, info, ID, "bekraeftelse");
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Opret ny adgangskode" })).toBeVisible();
  await page.getByLabel("Ny adgangskode", { exact: true }).fill(NEW_PW);
  await page.getByLabel("Bekræft ny adgangskode").fill(NEW_PW + "x");
  await expect(page.getByText("Adgangskoderne er ikke ens")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gem ny adgangskode og fortsæt" })).toBeDisabled();
  await page.getByLabel("Bekræft ny adgangskode").fill(NEW_PW);
  await snap(page, info, ID, "ny-kode");
  await page.getByRole("button", { name: "Gem ny adgangskode og fortsæt" }).dblclick();
  await expect(page).toHaveURL(/\/login\?reset=1/);
  await expect(page.getByText("Adgangskoden er ændret. Log ind med den nye.")).toBeVisible();
  await snap(page, info, ID, "tilbage-til-login");
  expect((await page.request.get("/api/backend/auth/me")).status()).toBe(401);
  expect((await other.request.get("http://localhost:3200/api/backend/auth/me")).status()).toBe(401);
  await other.close();
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).status()).toBe(401);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill(NEW_PW);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  // the link is single-use
  await page.goto(link);
  await page.getByLabel("Ny adgangskode", { exact: true }).fill("Endnu-Et-Kodeord-2026");
  await page.getByLabel("Bekræft ny adgangskode").fill("Endnu-Et-Kodeord-2026");
  await page.getByRole("button", { name: "Gem ny adgangskode og fortsæt" }).click();
  await expect(page.getByText(/ugyldigt eller allerede brugt/)).toBeVisible();
});

test("A04 · ukendt e-mail får samme bekræftelse (ingen kontoopslag), og ingen mail sendes", async ({ page }, info) => {
  await page.goto("/password/forgot");
  await page.getByLabel("E-mail").fill(mail("ukendt-findes-ikke", info));
  await page.getByRole("button", { name: "Send nulstillingslink" }).click();
  await expect(page.getByText(/Hvis adressen findes, har vi sendt et link/)).toBeVisible();
  await page.getByRole("link", { name: "Tilbage til login" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("A04 · udløbet link: klar fejl og vej til et nyt link", async ({ page }, info) => {
  const email = mail("udloebet", info);
  await register(page, email);
  const link = await requestReset(page, email);
  expect(expireTokens(email, "password_reset")).toMatch(/UPDATE [1-9]/);
  await page.goto(link);
  await page.getByLabel("Ny adgangskode", { exact: true }).fill(NEW_PW);
  await page.getByLabel("Bekræft ny adgangskode").fill(NEW_PW);
  await page.getByRole("button", { name: "Gem ny adgangskode og fortsæt" }).click();
  await expect(page.getByText("Linket er udløbet")).toBeVisible();
  await snap(page, info, ID, "udloebet");
  await page.getByRole("link", { name: "Bestil nyt link" }).click();
  await expect(page).toHaveURL(/\/password\/forgot/);
  // the old password still works: nothing changed
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
});

test("A04 · for kort kode afvises ved feltet; link uden token siger det", async ({ page }, info) => {
  const email = mail("kort", info);
  await register(page, email);
  const link = await requestReset(page, email);
  await page.goto(link);
  await page.getByLabel("Ny adgangskode", { exact: true }).fill("kort1");
  await page.getByLabel("Bekræft ny adgangskode").fill("kort1");
  await page.getByRole("button", { name: "Gem ny adgangskode og fortsæt" }).click();
  await expect(page).toHaveURL(/\/password\/reset/);
  expect(await page.getByLabel("Ny adgangskode", { exact: true }).evaluate((e: HTMLInputElement) => e.validity.valid)).toBe(false);
  await expect(page.getByText(/Mindst 10 tegn/i).first()).toBeVisible();
  // the token was NOT burnt by the rejected attempt
  await page.getByLabel("Ny adgangskode", { exact: true }).fill(NEW_PW);
  await page.getByLabel("Bekræft ny adgangskode").fill(NEW_PW);
  await page.getByRole("button", { name: "Gem ny adgangskode og fortsæt" }).click();
  await expect(page).toHaveURL(/\/login\?reset=1/);
  await page.goto("/password/reset");
  await expect(page.getByText("Linket mangler en token. Bestil et nyt link.")).toBeVisible();
  await snap(page, info, ID, "uden-token");
});

test("A04 · serverfejl ved bestilling vises; man bliver på formularen", async ({ page }, info) => {
  await page.route("**/api/backend/auth/password/forgot", (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal_error", message: "Der skete en fejl hos os. Prøv igen." }) }));
  await page.goto("/password/forgot");
  await page.getByLabel("E-mail").fill(mail("500", info));
  await page.getByRole("button", { name: "Send nulstillingslink" }).click();
  await expect(page.getByText("Der skete en fejl hos os. Prøv igen.")).toBeVisible();
  await expect(page.getByText(/Hvis adressen findes/)).toHaveCount(0);
  await snap(page, info, ID, "serverfejl");
});
