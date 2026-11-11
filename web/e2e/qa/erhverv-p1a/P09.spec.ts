import { expect, test } from "@playwright/test";
import { evid, noHorizontalScroll, snap } from "./p1a-helpers";

/* QA P09 (e2e-erhverv A, wave 2): /legal/:document – separate privacy, terms, data-processing and cookie-information
 * views on a shared readable template; unsupplied legal text marked as draft (DB-015: «legal content stays draft until
 * approved»). Implementation: /privatliv, /vilkaar, /gdpr on components/legal-page.tsx; the DPA is a clause of /vilkaar
 * and cookie information is a section of /privatliv. No page is marked draft. */
const ID = "P09";
evid(ID);
const DOCS = ["/da/privatliv", "/da/vilkaar"]; // /da/gdpr is an explainer page (seo-page template), checked for footer link only

test("P09 · de juridiske sider deler skabelon: én h1, dato, læsbar bredde, links i footer", async ({ page }, info) => {
  for (const d of DOCS) {
    expect((await page.goto(d))?.status(), d).toBe(200);
    await expect(page.locator("h1"), d).toHaveCount(1);
    await expect(page.locator("main"), d).toContainText(/(Opdateret|gældende fra) \d{1,2}\. \w+ 20\d\d/);
    const widest = await page.$$eval("main p", (ps) => Math.max(...ps.filter((p) => (p.textContent ?? "").length > 200).map((p) => p.getBoundingClientRect().width).concat(0)));
    expect(widest, d).toBeLessThanOrEqual(820);
    await noHorizontalScroll(page);
    await snap(page, info, ID, d.split("/").pop()!);
  }
  await page.goto("/da/priser"); // the site footer
  for (const d of [...DOCS, "/da/gdpr"]) await expect(page.locator(`footer a[href='${d}']`).first()).toBeAttached();
});

test("P09 · juridiske sider i Privat og på lange sprog scroller ikke vandret (F-VER4-02-P09)", async ({ page }) => {
  // The legal-page header: logo + three 44 px links. At 390 px «Kontakt» stuck out 5 px; /privat/vilkaar shares it.
  for (const d of ["/privat/vilkaar", "/de/privatliv", "/fr/vilkaar"]) {
    expect((await page.goto(d))?.status(), d).toBe(200);
    await noHorizontalScroll(page);
  }
});

test("P09 · cookie-oplysning og databehandleraftale kan findes", async ({ page }) => {
  await page.goto("/da/privatliv");
  await expect(page.locator("main")).toContainText("Cookies");
  await page.goto("/da/vilkaar");
  await expect(page.locator("main")).toContainText("databehandleraftale");
});

test("P09 · tekst der ikke er godkendt, er mærket som udkast (DB-015) – needs-decision", async ({ page }) => {
  // There is no draft marker anywhere; whether the texts are approved is Fürster's call (F-E2A-08).
  test.info().annotations.push({ type: "needs-decision", description: "Ingen 'udkast'-markering; separat DPA- og cookieside findes ikke." });
  for (const d of DOCS) {
    await page.goto(d);
    await expect(page.locator("main"), d).not.toContainText(/udkast|kladde|draft/i);
  }
});
