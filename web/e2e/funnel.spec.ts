import { expect, test, type Page } from "@playwright/test";
import { shot } from "./helpers";
import { localEstimate } from "../src/lib/funnel/api";

/** The two quiz-funnels in fake mode (web built with NEXT_PUBLIC_FUNNEL_FAKE=1 and NEXT_PUBLIC_PRIVAT_FAKE=1: the funnel
 *  API and the Privat app are simulated in the browser; nothing is sent, called or stored outside the tab).
 *  Run: NEXT_PUBLIC_FUNNEL_FAKE=1 NEXT_PUBLIC_PRIVAT_FAKE=1 npm run build && npm start, then
 *  NEXT_PUBLIC_FUNNEL_FAKE=1 npx playwright test e2e/funnel.spec.ts. Each journey runs at 390 and 1440 px. */

if (process.env.PW_CHROMIUM) test.use({ launchOptions: { executablePath: process.env.PW_CHROMIUM } });
const needsFake = () => test.skip(process.env.NEXT_PUBLIC_FUNNEL_FAKE !== "1", "kræver et web-build med NEXT_PUBLIC_FUNNEL_FAKE=1");
const CODE = "123456";

// ---------------------------------------------------------------- unit (no browser)

test.describe("enheder", () => {
  test("estimatet er et branchegennemsnit med kilde, aldrig 0", () => {
    const e = localEstimate("klinik", ["lunch", "after16"]);
    expect(e.missed_per_week).toBeGreaterThan(0);
    expect(e.source).toContain("Dialogbot");
    expect(localEstimate(undefined, []).missed_per_week).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------- helpers

async function noHorizontalScroll(page: Page) {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, "ingen vandret scroll").toBeLessThanOrEqual(0);
}

async function gate(page: Page, name: string, email: string) {
  await expect(page.locator("[data-gate='name']")).toBeVisible();
  await page.getByLabel("Navn").fill(name);
  await page.locator("[data-next]").click();
  await page.getByLabel("Mobil").fill("12 34 56 78");
  await page.locator("[data-next]").click();
  await page.getByLabel("E-mail").fill(email);
  await page.locator("[data-next]").click();
  await expect(page.locator("[data-gate='consent']")).toBeVisible();
  // Without the tick the code is not sent.
  await page.getByRole("button", { name: "Send kode" }).click();
  await expect(page.locator("#gate-consent-hint")).toContainText("Sæt kryds");
  await page.getByRole("checkbox", { name: /Dialogbot/ }).check();
  await page.getByRole("button", { name: "Send kode" }).click();
}

// ---------------------------------------------------------------- Erhverv

test.describe("Erhverv-funnel (/start)", () => {
  test.beforeEach(needsFake);

  test("annonce → 7 trin → kode → «Hun ringer nu» med resumé", async ({ page }, info) => {
    await page.goto("/start?b=klinik&h=stige&utm_source=e2e");
    await expect(page).toHaveURL(/\/start\/1\?b=klinik/);
    // The hook changes the headline; b= preselects the line of business.
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Telefonen ringer. Hvem tager den?");
    await expect(page.getByRole("radio", { name: "Klinik" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByText("Trin 1 af 7")).toBeVisible();
    await noHorizontalScroll(page);
    await shot(page, info, "funnel-erhverv-1");
    // The draft id lives in the cookie.
    expect((await page.context().cookies()).find((c) => c.name === "dialogbot_funnel")?.value).toMatch(/^fake-/);
    await page.getByRole("radio", { name: "Klinik" }).click();

    await expect(page).toHaveURL(/\/start\/2$/);
    await page.getByRole("combobox").fill("Fjord");
    await page.getByRole("option", { name: /Fjordgulv ApS/ }).click();
    await expect(page.locator("[data-place]")).toContainText("Havnegade 12");
    await shot(page, info, "funnel-erhverv-2");
    await page.locator("[data-next]").click();

    await expect(page).toHaveURL(/\/start\/3$/);
    await expect(page.locator("[data-estimate]")).toHaveCount(0);
    await page.getByRole("checkbox", { name: "Til frokost" }).click();
    await page.getByRole("checkbox", { name: "Efter kl. 16" }).click();
    const est = page.locator("[data-estimate] input");
    await expect(est).toBeVisible();
    await expect(page.locator("[data-estimate]")).toContainText("Kilde:");
    await est.fill("15");
    await shot(page, info, "funnel-erhverv-3");
    await page.locator("[data-next]").click();

    await expect(page).toHaveURL(/\/start\/4$/);
    await expect(page.locator("[data-next]")).toBeDisabled();
    await page.getByRole("checkbox", { name: /Booke tider/ }).click();
    await page.getByRole("checkbox", { name: /Tage imod beskeder/ }).click();
    await page.locator("[data-next]").click();

    await expect(page).toHaveURL(/\/start\/5$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Fjordgulv ApS");
    await expect(page.locator("[data-next]")).toBeDisabled();
    await expect(page.locator("[data-build]")).toHaveAttribute("data-build", "settled", { timeout: 30_000 });
    await expect(page.locator("[data-row='voice']")).toHaveAttribute("data-state", "done");
    await expect(page.locator("[data-row='number']")).toHaveAttribute("data-state", "done");
    await shot(page, info, "funnel-erhverv-5");
    await page.getByRole("button", { name: "Hør hende nu" }).click();

    await expect(page).toHaveURL(/\/start\/6$/);
    await expect(page.getByText("Trin 6 af 7")).toBeVisible();
    await gate(page, "Mette Jensen", `e2e-${info.project.name}@example.com`);

    await expect(page).toHaveURL(/\/start\/7$/);
    await expect(page.getByText("12 34 56 78")).toBeVisible();
    await expect(page.locator("[data-resend]")).toBeDisabled();
    // A wrong code stays on the step and says so.
    await page.getByLabel("Kode fra SMS").fill("000000");
    await expect(page.locator("#code-hint")).toContainText("passer ikke");
    await page.getByLabel("Kode fra SMS").fill(CODE);

    await expect(page).toHaveURL(/\/start\/klar$/, { timeout: 15_000 });
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Hun ringer nu til 12 34 56 78");
    await expect(page.locator("[data-call]")).toHaveAttribute("data-call", "done", { timeout: 30_000 });
    await expect(page.locator("[data-summary]")).toContainText("Fjordgulv ApS");
    await expect(page.locator("[data-make-hers]")).toHaveAttribute("href", "/opsaetning/1");
    await expect(page.getByRole("button", { name: "Hør det igen" })).toHaveCount(0); // no audio from the fake
    await noHorizontalScroll(page);
    await shot(page, info, "funnel-erhverv-klar");
  });

  // The business front page sits behind the preview gate in CI, so its «Prøv på 2 minutter» button is not checked here.
  test("dybt link forbi det besvarede sendes tilbage", async ({ page }) => {
    await page.goto("/start/5");
    await expect(page).toHaveURL(/\/start\/1$/);
  });
});

// ---------------------------------------------------------------- Privat

test.describe("Privat-funnel (/privat/start)", () => {
  test.beforeEach(needsFake);

  test("6 trin → kode → Min dag med velkomst", async ({ page }, info) => {
    await page.goto("/privat/start?h=1605");
    await expect(page).toHaveURL(/\/privat\/start\/1\?h=1605/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Hvad har du udsat?");
    await expect(page.getByText("Kl. 16.05 – og du har stadig ikke ringet")).toBeVisible();
    await expect(page.locator("[data-theme='privat']")).toHaveCount(1);
    await noHorizontalScroll(page);
    await shot(page, info, "funnel-privat-1");
    await page.getByRole("checkbox", { name: "Tandlægen" }).click();
    await page.getByRole("checkbox", { name: "Cyklen til eftersyn" }).click();
    await page.locator("[data-next]").click();

    await expect(page).toHaveURL(/\/privat\/start\/2$/);
    await page.getByRole("radio", { name: /Familie med børn/ }).click();

    await expect(page).toHaveURL(/\/privat\/start\/3$/);
    await expect(page.locator("[data-example]")).toHaveCount(0);
    await page.getByRole("radio", { name: "Værkstedet" }).click();
    await expect(page.locator("[data-example='workshop']")).toContainText("Mette Jensen");
    await shot(page, info, "funnel-privat-3");
    await page.locator("[data-next]").click();

    await expect(page).toHaveURL(/\/privat\/start\/4$/);
    await page.getByRole("radio", { name: /Om morgenen/ }).click();

    await expect(page).toHaveURL(/\/privat\/start\/5$/);
    await expect(page.locator("[data-build]")).toHaveAttribute("data-build", "settled", { timeout: 30_000 });
    await expect(page.locator("[data-summary]")).toHaveText("2 opgaver · 2 lister · 1 opkald Peter vil tage");
    await expect(page.locator("[data-row='first_call']")).toContainText("tandlægen");
    await shot(page, info, "funnel-privat-5");
    await page.getByRole("button", { name: "Se min dag" }).click();

    await expect(page).toHaveURL(/\/privat\/start\/6$/);
    await expect(page.getByText("Trin 6 af 6")).toBeVisible();
    await gate(page, "Mette Jensen", `e2e-privat-${info.project.name}@example.com`);
    await expect(page.locator("[data-code]")).toBeVisible();
    await page.getByLabel("Kode fra SMS").fill(CODE);

    await expect(page).toHaveURL(/\/privat\/dag\?velkommen=1$/, { timeout: 15_000 });
    await expect(page.locator("[data-welcome]")).toContainText("Peter har sat din dag op");
    await shot(page, info, "funnel-privat-dag");
    await page.getByRole("button", { name: "Luk" }).click();
    await expect(page.locator("[data-welcome]")).toHaveCount(0);
  });

  test("Privat-forsiden har indgangen", async ({ page }) => {
    await page.goto("/privat");
    await expect(page.locator("[data-funnel-entry]").first()).toHaveAttribute("href", "/privat/start");
  });
});
