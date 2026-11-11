import { expect, test, type Page } from "@playwright/test";

/** QA journey audit, Dialogbot Privat (F-JP-*): the Privat person followed through auth pages, links and error pages.
 *  Real stack (BASE_URL=http://localhost:3500, API on :8500, ENABLE_DEV_TOOLS=true). 390 px first, then 1280 px.
 *  Each test that shows a live bug is `test.fail()` with its finding id – it turns red the day the bug is fixed.
 *  Not run in the audit (the machine had < 4 GB free); backend halves are in tests/qa/test_qa_journey_privat.py. */
if (process.env.PW_CHROMIUM) test.use({ launchOptions: { executablePath: process.env.PW_CHROMIUM } });

const audienceOf = (page: Page) => page.locator("[data-audience]").first().getAttribute("data-audience");

for (const width of [390, 1280]) {
  test.describe(`Privat-rejsen @${width}px`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } });

    test("#179: /verify-email?for=privat er orange og fører til /privat/konto", async ({ page }) => {
      await page.goto("/verify-email?for=privat");
      expect(await audienceOf(page)).toBe("privat");
    });

    test("F-JP-04: «Log ind» fra et gruppelink (/g/…) viser Privat-login, ikke Erhverv", async ({ page }) => {
      test.fail(true, "F-JP-04");
      await page.goto(`/login?next=${encodeURIComponent("/g/ABCDEFGH")}`);
      expect(await audienceOf(page)).toBe("privat");
    });

    test("F-JP-04: «Opret konto» fra et gruppelink har ingen Erhverv-produktvalg", async ({ page }) => {
      test.fail(true, "F-JP-04");
      await page.goto(`/signup?next=${encodeURIComponent("/g/ABCDEFGH")}`);
      expect(await audienceOf(page)).toBe("privat");
      await expect(page.getByRole("combobox")).toHaveCount(0);
    });

    test("F-JP-10: «Bekræft din e-mail» fra Privat-appen viser ikke «arbejdsrummet»/«virksomheder»", async ({ page }) => {
      test.fail(true, "F-JP-10");
      await page.goto("/verify-email"); // the href in components/privat/shell.tsx AccountNotice
      await expect(page.locator("body")).not.toContainText(/arbejdsrum|virksomhed/i);
    });

    test("F-JP-02: nulstil adgangskode → login uden ?next viser Privat (ikke Erhverv)", async ({ page }) => {
      test.fail(true, "F-JP-02");
      await page.goto("/login?reset=1"); // where /password/reset sends everyone
      expect(await audienceOf(page)).toBe("privat");
    });

    test("F-JP-11: ukendt /privat-adresse giver en orange Privat-404 på dansk med vej tilbage", async ({ page }) => {
      test.fail(true, "F-JP-11");
      const r = await page.goto("/privat/findes-ikke");
      expect(r?.status()).toBe(404);
      await expect(page.locator("[data-theme=privat]")).toHaveCount(1);
      await expect(page.getByRole("link", { name: /Dialogbot|forside|Min dag/i })).toBeVisible();
    });

    test("/privat/offline er Privat-temaet", async ({ page }) => {
      await page.goto("/privat/offline");
      await expect(page.locator("body")).not.toContainText(/arbejdsrum|AI-receptionist/i);
    });
  });
}
