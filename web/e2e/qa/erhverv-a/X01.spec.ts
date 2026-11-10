import { expect, test, type Page } from "@playwright/test";
import { PREVIEW_CODE } from "../../helpers";

/* QA X01 (e2e-erhverv A): indgangssiden "/" – vælg Erhverv/Privat, valget huskes (db_aud) og "/" sender videre
 * ved næste besøg; Erhverv-landing ligger på /erhverv. Source: web/src/proxy.ts (audienceDoor, rememberAudience),
 * web/src/components/audience-memory.tsx. */
const EVID = "../qa/evidence/X01";
const CSRF = { "x-requested-with": "dialogbot" };

async function unlock(page: Page) {
  const r = await page.request.post("/api/preview/unlock", { headers: CSRF, data: { code: PREVIEW_CODE, next: "/" } });
  expect(r.ok()).toBeTruthy();
}
const aud = async (page: Page) => (await page.context().cookies()).find((c) => c.name === "db_aud");

test("X01 · første besøg viser to døre hurtigt; prefetch husker intet; Erhverv huskes og / sender videre", async ({ page }, info) => {
  await unlock(page);
  const t0 = Date.now();
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/da$/);
  const business = page.getByRole("link", { name: /Til virksomheder/ });
  const priv = page.getByRole("link", { name: /Til dig derhjemme/ });
  await expect(business).toHaveAttribute("href", /\/erhverv$/);
  await expect(priv).toHaveAttribute("href", "/privat");
  const ms = Date.now() - t0;
  info.annotations.push({ type: "entry-doors-ready-ms", description: String(ms) });
  expect(ms, "the two doors are on the page within 3 s").toBeLessThan(3000);
  // the entry page is never shared-cached (it depends on the cookie)
  const head = await page.request.get("/da", { maxRedirects: 0 });
  expect(head.headers()["cache-control"]).toContain("no-store");
  // Next prefetches both doors – a prefetch must not become the remembered audience
  await page.waitForLoadState("networkidle");
  await priv.scrollIntoViewIfNeeded();
  await business.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  expect(await aud(page)).toBeUndefined();
  await page.screenshot({ path: `${EVID}/${info.project.name}-indgang.png` });

  await business.click();
  await expect(page).toHaveURL(/\/da\/erhverv$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect.poll(async () => (await aud(page))?.value).toBe("erhverv");
  const c = (await aud(page))!;
  expect(c.expires - Date.now() / 1000).toBeGreaterThan(300 * 24 * 3600); // remembered ~1 year
  expect(c.sameSite).toBe("Lax");
  // next visit: "/" goes straight to Erhverv, also from another language and with campaign parameters kept
  await page.goto("/");
  await expect(page).toHaveURL(/\/da\/erhverv$/);
  await page.goto("/?utm_source=qa&anbefalet=abc");
  await expect(page).toHaveURL(/\/da\/erhverv\?utm_source=qa&anbefalet=abc$/);
  await page.goto("/en");
  await expect(page).toHaveURL(/\/en\/erhverv$/);
  // reload of /erhverv keeps the choice
  await page.reload();
  expect((await aud(page))?.value).toBe("erhverv");
  // reset shows the entry again and clears the memory
  // (the /en visit above remembered English as the language, so the entry is now /en)
  await page.goto("/?aud=reset");
  await expect(page).toHaveURL(/\/en\?aud=reset$/);
  await expect(page.locator('a[href$="/erhverv"]').first()).toBeVisible();
  await expect.poll(async () => (await aud(page))?.value ?? "").toBe("");
  await page.goto("/");
  await expect(page).toHaveURL(/\/en$/);
  await page.screenshot({ path: `${EVID}/${info.project.name}-efter-reset.png` });
});

test("X01 · Privat huskes; et ugyldigt cookie-indhold viser indgangen; direkte /erhverv-besøg husker også", async ({ page, context }, info) => {
  await unlock(page);
  await page.goto("/");
  await page.getByRole("link", { name: /Til dig derhjemme/ }).click();
  await expect(page).toHaveURL(/\/privat$/);
  await expect.poll(async () => (await aud(page))?.value).toBe("privat");
  await page.goto("/");
  await expect(page).toHaveURL(/\/privat$/);
  await page.screenshot({ path: `${EVID}/${info.project.name}-privat-husket.png` });

  // a tampered cookie must never redirect anywhere odd
  await context.addCookies([{ name: "db_aud", value: "https://evil.example", url: "http://localhost:3000" }]);
  await page.goto("/");
  await expect(page).toHaveURL(/\/da$/);

  // a full page load of /erhverv (e.g. from an ad) remembers Erhverv
  await context.clearCookies({ name: "db_aud" });
  await page.goto("/erhverv");
  await expect(page).toHaveURL(/\/da\/erhverv$/);
  expect((await aud(page))?.value).toBe("erhverv");
  await page.goto("/");
  await expect(page).toHaveURL(/\/da\/erhverv$/);
});

test("X01 · uden forhåndskode: / går til forhåndssiden, og en husket dør åbner ikke den skjulte forside", async ({ page, context }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/preview$/);
  await context.addCookies([{ name: "db_aud", value: "erhverv", url: "http://localhost:3000" }]);
  await page.goto("/");
  await expect(page).toHaveURL(/\/preview\?next=%2Ferhverv$/);
});
