import { expect, test, type Page } from "@playwright/test";
import { DEMO_PASSWORD, PREVIEW_CODE, uniqueEmail } from "../../helpers";

/* QA A01 (e2e-erhverv A): /signup – independent signup that preserves reception / campaigns / both.
 * Source: web/src/app/signup/page.tsx, app/modules/identity/service.py:register. */
const EVID = "../qa/evidence/A01";
const CSRF = { "x-requested-with": "dialogbot" };
async function unlock(page: Page) {
  expect((await page.request.post("/api/preview/unlock", { headers: CSRF, data: { code: PREVIEW_CODE, next: "/signup" } })).ok()).toBeTruthy();
}
const me = async (page: Page) => (await (await page.request.get("/api/backend/auth/me")).json()) as { signup_intent: string | null; email_verified: boolean };

for (const [intent, label] of [["reception", null], ["campaigns", null], ["both", "Begge"]] as const) {
  test(`A01 · ?intent=${intent} står i formularen og gemmes på kontoen`, async ({ page }, info) => {
    await unlock(page);
    await page.goto(`/signup?intent=${intent}`);
    await expect(page.getByLabel("Jeg vil starte med")).toHaveValue(intent);
    await page.getByLabel("Dit navn").fill("QA Tilmelding");
    await page.getByLabel("E-mail").fill(uniqueEmail(`a01${intent}`, info));
    await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
    const submit = page.getByRole("button", { name: "Opret konto" });
    await submit.dblclick(); // double submit must not produce an error or a second account
    await expect(page).toHaveURL(/\/verify-email/);
    expect((await me(page)).signup_intent).toBe(intent);
    if (label) await page.screenshot({ path: `${EVID}/${info.project.name}-${intent}.png`, fullPage: true });
  });
}

test("A01 · uden ?intent kan besøgende selv vælge «kampagner», og valget bevares", async ({ page }, info) => {
  await unlock(page);
  await page.goto("/signup");
  await expect(page.getByLabel("Jeg vil starte med")).toHaveValue("reception");
  await page.getByLabel("Jeg vil starte med").selectOption("campaigns");
  await page.getByLabel("Dit navn").fill("QA Valg");
  await page.getByLabel("E-mail").fill(uniqueEmail("a01valg", info));
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.screenshot({ path: `${EVID}/${info.project.name}-valg.png`, fullPage: true });
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/verify-email/);
  expect((await me(page)).signup_intent).toBe("campaigns");
});

test("A01 · fejl: kort adgangskode og eksisterende e-mail vises ved feltet; intet halvt login", async ({ page }, info) => {
  await unlock(page);
  await page.goto("/signup?intent=both");
  await page.getByLabel("Dit navn").fill("QA Fejl");
  await page.getByLabel("E-mail").fill("owner@fjordgulv.example");
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page.getByText(/allerede registreret/)).toBeVisible();
  await expect(page).toHaveURL(/\/signup/);
  expect((await page.request.get("/api/backend/auth/me")).status()).toBe(401);
  await expect(page.getByLabel("Jeg vil starte med")).toHaveValue("both");
  await page.screenshot({ path: `${EVID}/${info.project.name}-fejl.png`, fullPage: true });
});

test("A01 · et ukendt ?intent i linket må ikke låse formularen", async ({ page }, info) => {
  await unlock(page);
  await page.goto("/signup?intent=kampagne"); // typo in an ad / partner link
  await page.getByLabel("Dit navn").fill("QA Ukendt");
  await page.getByLabel("E-mail").fill(uniqueEmail("a01ukendt", info));
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  const shown = await page.getByLabel("Jeg vil starte med").evaluate((s: HTMLSelectElement) => s.options[s.selectedIndex]?.value);
  await page.getByRole("button", { name: "Opret konto" }).click();
  await page.screenshot({ path: `${EVID}/${info.project.name}-ukendt-intent.png`, fullPage: true });
  await expect(page, `select shows «${shown}» but the form sends the raw query value`).toHaveURL(/\/verify-email/, { timeout: 8_000 });
  expect((await me(page)).signup_intent).toBe(shown);
});
