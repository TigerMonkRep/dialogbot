import { expect, test, type Page } from "@playwright/test";
import { amountInput, imgSrc, money, parseAmount } from "../src/lib/privat/wish";

/** Ønskesedler: wishes, «Deles om en gave» and «Design ønskeseddel». The journeys run in fake mode
 *  (NEXT_PUBLIC_PRIVAT_FAKE=1 next dev; BASE_URL=… npx playwright test e2e/oensker.spec.ts). The secrecy rules are tested
 *  against the real backend in tests/test_privat_wishes.py. */
if (process.env.PW_CHROMIUM) test.use({ launchOptions: { executablePath: process.env.PW_CHROMIUM } });

test.describe("beløb", () => {
  test("format og indtastning i mindste enhed", () => {
    expect(money(125000, "DKK", "da")).toBe("1.250 kr.");
    expect(money(300000, "DKK", "da")).toBe("3.000 kr.");
    expect(money(12550, "DKK", "da")).toBe("125,50 kr.");
    expect(parseAmount("1.250", "DKK")).toBe(125000);
    expect(parseAmount("1250,50 kr.", "DKK")).toBe(125050);
    expect(parseAmount("750", "DKK")).toBe(75000);
    expect(parseAmount("1,250.00", "EUR")).toBe(125000);
    expect(parseAmount("abc", "DKK")).toBeNull();
    expect(amountInput(175000, "DKK", "da")).toBe("1750");
    expect(imgSrc("local://privat-files/a/b.webp?exp=1&sig=x")).toBe("/api/backend/privat/dev-files?key=a%2Fb.webp&exp=1&sig=x");
  });
});

const needsFake = () => test.skip(process.env.NEXT_PUBLIC_PRIVAT_FAKE !== "1", "kræver et web-build med NEXT_PUBLIC_PRIVAT_FAKE=1");

async function open(page: Page, path: string) {
  await page.addInitScript(() => sessionStorage.setItem("dialogbot-privat-fake-login", "1"));
  await page.goto(path);
  await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false");
}

test.describe("ønskesedler (simuleret)", () => {
  test.beforeEach(() => needsFake());

  test("fællesgave: tilsagn, for højt beløb foreslår restbeløbet, ingen penge trækkes", async ({ page }) => {
    await open(page, "/privat/opgaver/s1");
    const card = page.locator("[data-testid=wish-card]:visible", { hasText: "Weekend i sommerhus" }).last();
    await expect(card.getByText("1.250 kr. af 3.000 kr. aftalt")).toBeVisible();
    await expect(card.getByText("1.750 kr. mangler")).toBeVisible();
    await card.getByTestId("join-gift").click();
    await expect(page.getByText("Du tilmelder dig med et beløb. Der bliver ikke trukket penge.").first()).toBeVisible();
    await page.getByLabel(/Dit beløb/).fill("2000");
    await page.getByRole("button", { name: /Meld mig til/ }).click();
    await expect(page.getByTestId("pledge-proposal")).toContainText("1.750 kr.");
    await page.getByRole("button", { name: "Ja, 1.750 kr." }).click();
    await expect(page.getByTestId("pledge-done")).toBeVisible();
    await page.getByRole("button", { name: "OK" }).click();
    await expect(card.getByText("3.000 kr. af 3.000 kr. aftalt")).toBeVisible();
    await expect(card.getByText("Fuldt tilsagn")).toBeVisible();  // never «Købt» by itself
  });

  test("opret selv: ønske uden link med pris, størrelse og fællesgave", async ({ page }) => {
    await open(page, "/privat/opgaver");
    await page.locator("#privat-ask-tasks:visible, #privat-ask:visible").first().fill("Lav en ønskeliste med te");
    await page.locator("#privat-ask-tasks:visible, #privat-ask:visible").first().press("Enter");
    await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false");
    await page.goto("/privat/opgaver");
    await page.getByRole("button", { name: /Ønskeliste/ }).first().click();
    await page.locator("[data-testid=add-wish]:visible").last().click();
    await page.getByRole("button", { name: /Opret selv/ }).click();
    const form = page.getByTestId("wish-form");
    await form.getByLabel("Titel").fill("Racercykel");
    await form.getByLabel(/^Pris/).fill("3.499");
    await form.getByPlaceholder("Fx str. 42").fill("54 cm");
    await form.getByTestId("allow-gift").check();
    await expect(form.getByTestId("gift-target")).toHaveValue("3.499");  // the price is proposed as the target
    await form.getByTestId("gift-target").fill("3000");
    await form.getByRole("button", { name: "Gem ønske" }).click();
    const card = page.locator("[data-testid=wish-card]:visible", { hasText: "Racercykel" }).last();
    await expect(card.getByText("3.499 kr.")).toBeVisible();
    await expect(card.getByText("Fællesgave")).toBeVisible();
    await expect(page.locator("[data-testid=wish-card]:visible", { hasText: "Te" }).last().getByText("Pris ikke angivet")).toBeVisible();
  });

  test("design: tema, hilsen og nulstil påvirker ikke ønskerne", async ({ page }) => {
    await open(page, "/privat/opgaver");
    await page.locator("#privat-ask-tasks:visible, #privat-ask:visible").first().fill("Lav en ønskeliste med te og kaffe");
    await page.locator("#privat-ask-tasks:visible, #privat-ask:visible").first().press("Enter");
    await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false");
    await page.goto("/privat/opgaver");
    await page.getByRole("button", { name: /Ønskeliste/ }).first().click();
    const grid = page.locator("[data-testid=wish-grid]:visible").last();
    await expect(grid.locator("[data-testid=wish-card]")).toHaveCount(2);
    const before = 2;
    await page.locator("[data-testid=design-open]:visible").last().click();
    await page.getByTestId("theme-jul").click();
    await page.getByLabel("Undertitel eller hilsen").fill("God jul!");
    await expect(page.getByTestId("preview-mobile")).toContainText("God jul!");
    await page.getByRole("tab", { name: "Computer" }).click();
    await expect(page.getByTestId("preview-desktop")).toBeVisible();
    await page.getByTestId("design-save").click();
    await expect(page.locator("[data-testid=wish-cover]:visible").last()).toHaveAttribute("data-theme", "jul");
    await expect(page.locator("[data-testid=wish-cover]:visible").last()).toContainText("God jul!");
    await page.locator("[data-testid=design-open]:visible").last().click();
    await page.getByRole("button", { name: "Nulstil til tema" }).click();
    await page.getByTestId("design-save").click();
    await expect(grid.locator("[data-testid=wish-card]")).toHaveCount(before);
  });
});
