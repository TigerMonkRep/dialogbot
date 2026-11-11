import { expect, test, type Page, type TestInfo } from "@playwright/test";
import type { Server } from "node:http";
import { DEMO_PASSWORD, PREVIEW_CODE, latestMailLink, serve, shot, uniqueEmail } from "../helpers";

/* Guide trin 1 (Fürster 11/11 23:20: «den registrerer ikke step 1 … gemmer ikke tingene på step 1»).
 * A real new Erhverv customer: /signup → verify-mail link → /opsaetning/1 → creates the workspace → fills trin 1 in four
 * ways: (a) «Videre», (b) straight to the next step in the stepper, (c) reload, (d) fetch from the website first.
 * Every way: the backend has the data, the stepper marks trin 1 done, and the data is there on return and after reload.
 * The save calls are slowed down like on Render (≈1.2 s) – a quick second edit must never be lost to a version conflict. */
const SITE_PORT = Number(process.env.E2E_SITE_PORT ?? 4000);
const servers: Server[] = [];
test.afterEach(async () => { for (const s of servers.splice(0)) await new Promise((r) => s.close(r)); });

async function unlock(page: Page) {
  await page.goto("/preview");
  const code = page.getByLabel("Invitationskode");
  if (await code.isVisible().catch(() => false)) {
    await code.fill(PREVIEW_CODE);
    await page.getByRole("button", { name: "Lås op og se forsiden" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/preview"));
  }
}

/** Sign up as a new business in the browser, follow the verify link and create the workspace on trin 1. */
async function signup(page: Page, info: TestInfo, company: string) {
  await unlock(page);
  await page.goto("/signup?intent=reception");
  await page.getByLabel("Dit navn").fill("Rebotti Ejer");
  await page.getByLabel("E-mail").fill(uniqueEmail("trin1", info));
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/verify-email/);
  await page.goto(await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/));
  await page.getByRole("link", { name: /Fortsæt til arbejdsrum/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/1/);
  await page.getByLabel("Navn (som den siger det)").fill(company);
  await page.getByRole("button", { name: "Videre" }).click();
  await expect(page.getByLabel("Hvad I laver – én sætning")).toBeVisible({ timeout: 15_000 });
  const ws = (await (await page.request.get("/api/backend/workspaces")).json()) as { id: string; name: string }[];
  return ws.find((w) => w.name === company)!.id;
}

/** Render-like latency on every save of trin 1. */
async function slowSaves(page: Page, ms = 1200) {
  await page.route(/\/api\/backend\/workspaces\/[^/]+\/(profile|goals|languages)$/, async (r) => {
    if (r.request().method() === "PUT") await new Promise((res) => setTimeout(res, ms));
    await r.fallback();
  });
}

const profile = async (page: Page, wsId: string) => (await (await page.request.get(`/api/backend/workspaces/${wsId}/profile`)).json()) as Record<string, string | null>;

/** Type trin 1 the way a person does: field after field, without waiting for «Gemt» in between. */
async function fillStep1(page: Page) {
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill("+45 86 12 34 56");
  await page.getByLabel("Hvad I laver – én sætning").fill("Italiensk restaurant og take-away i Aarhus");
  await page.getByLabel("Åbningstider").fill("Man–fre 11–22");
  await page.getByText("CVR og adresse (valgfrit)").click();
  await page.getByLabel("Adresse", { exact: true }).fill("Jægergårdsgade 10");
  await page.getByLabel("Postnummer").fill("8000");
  await page.getByLabel("By").fill("Aarhus C");
}

const WANT = { phone: "+45 86 12 34 56", description: "Italiensk restaurant og take-away i Aarhus", address_line: "Jægergårdsgade 10", postal_code: "8000", city: "Aarhus C" };

/** Trin 1 is marked done in the stepper (check mark + «fuldført» for screen readers) when you are on another step. */
async function step1Done(page: Page) {
  const link = page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: /Trin 1/ });
  await expect(link.locator(".material-symbols-outlined")).toHaveText("check");
  await expect(link).toHaveAccessibleName(/fuldført/);
}

/** Back on trin 1 (and after a reload) every field shows what was typed. */
async function step1Shows(page: Page) {
  await expect(page.getByLabel("Telefonnummer, kunderne ringer til")).toHaveValue(WANT.phone);
  await expect(page.getByLabel("Hvad I laver – én sætning")).toHaveValue(WANT.description);
  await expect(page.getByLabel("Åbningstider")).toHaveValue(/11.*22/);
  await page.getByText("CVR og adresse (valgfrit)").click();
  await expect(page.getByLabel("Adresse", { exact: true })).toHaveValue(WANT.address_line);
  await expect(page.getByLabel("By")).toHaveValue(WANT.city);
}

test("Trin 1 (a) · udfyld og tryk «Videre»: gemt, trin 1 fuldført, data står der ved retur og efter reload", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti A ${info.project.name} ${Date.now()}`);
  await slowSaves(page);
  await fillStep1(page);
  await page.getByRole("button", { name: /Videre til trin/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/[23]$/, { timeout: 20_000 });
  expect(await profile(page, wsId)).toMatchObject(WANT);
  await step1Done(page);
  await shot(page, info, "trin1-a-videre");
  await page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: /Trin 1/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/1$/);
  await step1Shows(page);
  await page.reload();
  await step1Shows(page);
});

test("Trin 1 (b) · udfyld og klik straks trin 2 i trinlinjen: intet går tabt, trin 1 fuldført", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti B ${info.project.name} ${Date.now()}`);
  await slowSaves(page);
  await fillStep1(page);
  // no pause: the stepper link right after the last keystroke
  await page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: /Trin 2/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/[23]$/, { timeout: 20_000 }); // trin 2 is skipped without booking
  expect(await profile(page, wsId)).toMatchObject(WANT);
  await step1Done(page);
  await shot(page, info, "trin1-b-trinlinje");
  await page.goto("/opsaetning/1");
  await step1Shows(page);
});

test("Trin 1 (c) · udfyld og genindlæs siden: det skrevne er gemt og står der igen", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti C ${info.project.name} ${Date.now()}`);
  await slowSaves(page);
  await fillStep1(page);
  await page.reload(); // straight away – the browser's own reload, before any pause has run out
  await step1Shows(page);
  expect(await profile(page, wsId)).toMatchObject(WANT);
  await page.goto("/opsaetning/3");
  await step1Done(page);
  await shot(page, info, "trin1-c-reload");
});

test("Trin 1 (d) · hent fra hjemmesiden først, ret derefter trin 1: alt gemmes, trin 1 fuldført", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti D ${info.project.name} ${Date.now()}`);
  servers.push(await serve(SITE_PORT, `<!doctype html><html lang="da"><head><title>Rebotti</title></head><body>
    <h1>Rebotti</h1><p>Italiensk restaurant i Aarhus med pizza og pasta.</p>
    <footer>Rebotti ApS · Jægergårdsgade 10 · 8000 Aarhus C · CVR 12345674 · Ring på 70 12 34 56 · Man-fre 11-22</footer></body></html>`));
  await slowSaves(page);
  await page.getByLabel("Hjemmesidens adresse").fill(`http://127.0.0.1:${SITE_PORT}/`);
  await page.getByRole("button", { name: /^Hent/ }).click();
  await expect(page.getByText(/Fundet på/)).toBeVisible({ timeout: 30_000 });
  // the owner corrects what the site said, quickly, field after field
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill(WANT.phone);
  await page.getByLabel("Hvad I laver – én sætning").fill(WANT.description);
  await page.getByLabel("Åbningstider").fill("Man–fre 11–22");
  await page.getByText("CVR og adresse (valgfrit)").click();
  await page.getByLabel("Adresse", { exact: true }).fill(WANT.address_line);
  await page.getByLabel("Postnummer").fill(WANT.postal_code);
  await page.getByLabel("By").fill(WANT.city);
  await expect(page.getByRole("status").getByText(/^Gemt/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Siden er ændret et andet sted.")).toHaveCount(0);
  expect(await profile(page, wsId)).toMatchObject({ ...WANT, website_url: `http://127.0.0.1:${SITE_PORT}/` });
  await page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: /Trin 3/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/3$/);
  await step1Done(page);
  await shot(page, info, "trin1-d-hjemmeside");
  await page.goto("/opsaetning/1");
  await step1Shows(page);
  await page.reload();
  await step1Shows(page);
  await expect(page.getByLabel("Hjemmesidens adresse")).toHaveValue(`http://127.0.0.1:${SITE_PORT}/`);
});

test("Trin 1 (e) · hjemmeside skrevet som «rebotti.dk» (som feltets eksempel): resten af trin 1 gemmes stadig", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti E ${info.project.name} ${Date.now()}`);
  await page.getByLabel("Hjemmesidens adresse").fill("rebotti.dk");
  await fillStep1(page);
  await expect(page.getByRole("status").getByText(/^Gemt/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(await profile(page, wsId)).toMatchObject({ ...WANT, website_url: "https://rebotti.dk" });
  await page.getByRole("button", { name: /Videre til trin/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/[23]$/);
  await step1Done(page);
  await shot(page, info, "trin1-e-domaene");
});
