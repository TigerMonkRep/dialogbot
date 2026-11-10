import { expect, test } from "@playwright/test";
import { DEMO_PASSWORD, freshOwner } from "../../helpers";
import { CSRF, EVID } from "./d-helpers";

/* S08 – /app/settings/profile: «Personal details, interface language, password/security, sessions and sign out.»
 * The route is a permanent redirect to /app/konto (right column «dig»). */
test("S08 · grænsefladesprog gemmes på brugeren og følger med efter reload; log ud fjerner adgangen", async ({ page }, info) => {
  const { email } = await freshOwner(page, info);
  await page.goto("/app/settings/profile");
  await expect(page).toHaveURL(/\/app\/konto$/);
  await expect(page.getByText(`${email} · ejer`)).toBeVisible();
  await expect(page.getByRole("link", { name: "Skift adgangskode" })).toHaveAttribute("href", "/password/forgot");
  await expect(page.getByText(/Logget ind på 1 enhed/)).toBeVisible();
  await page.getByText("Sprog", { exact: true }).first().scrollIntoViewIfNeeded();
  const lang = page.locator("select").filter({ has: page.locator('option[value="en"]') }).last();
  await lang.selectOption("en");
  await expect.poll(async () => (await (await page.request.get("/api/backend/auth/me")).json()).interface_language, { timeout: 10_000 }).toBe("en");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", /^en/);
  await page.screenshot({ path: `${EVID("S08")}/${info.project.name}-engelsk.png`, fullPage: true });
  await lang.selectOption("da");
  await expect.poll(async () => (await (await page.request.get("/api/backend/auth/me")).json()).interface_language).toBe("da");
  await page.reload();
  await page.getByRole("button", { name: "Log ud" }).click();
  await page.waitForURL(/\/login/);
  expect((await page.request.get("/api/backend/auth/me")).status()).toBe(401);
  await page.goto("/app/konto");
  await expect(page).toHaveURL(/\/login/);
});

test("S08 · anden enhed: sessionen vises, og den kan logges ud herfra; navnet kan rettes", async ({ page, browser }, info) => {
  const { email } = await freshOwner(page, info);
  const other = await browser.newContext({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1" });
  const op = await other.newPage();
  expect((await op.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  await page.goto("/app/konto");
  await expect(page.getByText(/Logget ind på 2 enheder/)).toBeVisible();
  await expect(page.getByText(/Safari på iOS/)).toBeVisible();
  await page.screenshot({ path: `${EVID("S08")}/${info.project.name}-sessioner.png`, fullPage: true });
  // requirement: sessions with sign-out; personal details editable (PATCH /auth/me supports display_name)
  await expect(page.getByRole("button", { name: /Log ud.*(iOS|enhed)|Log enheden ud|Log alle andre ud/ })).toBeVisible({ timeout: 3000 });
  await expect(page.getByLabel(/Navn/)).toBeEditable({ timeout: 3000 });
  await other.close();
});
