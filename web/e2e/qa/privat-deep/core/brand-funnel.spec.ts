import { expect, test } from "@playwright/test";
import { API, noHorizontalScroll, shot, stackUp, uniqueIp } from "./pk";

/** PC-BRAND-01 (topvælger Erhverv/Privat huskes; samme logo; Privat er orange) og PC-FUN-01 (CTA «Prøv gratis i 14 dage»
 *  → login/signup → Stripe-checkout, aldrig demo-Dag). Anonym besøgende, frisk browser-kontekst pr. test. */
test.beforeEach(async ({ request }) => { test.skip(!(await stackUp(request)), "kræver Privat-stakken på :8400"); });

const logoSvg = async (page: import("@playwright/test").Page) =>
  page.locator("header a").first().locator("svg").first().evaluate((el) => el.outerHTML.replace(/\s(class|style)="[^"]*"/g, ""));

test("PC-BRAND-01: vælgeren skifter, huskes efter reload og i ny fane; samme logo; Privat orange", async ({ page, context }, info) => {
  await context.setExtraHTTPHeaders({ "x-real-ip": uniqueIp() });
  await page.goto("/?aud=reset");
  const chooser = page.getByRole("navigation", { name: "Vælg: virksomhed eller privat" }).first();
  await expect(chooser).toBeVisible();
  await shot(page, info, "PC-BRAND-01", "entry");
  const erhvervLogo = await logoSvg(page);
  await chooser.getByRole("link", { name: /Privat/ }).click();
  await expect(page).toHaveURL(/\/privat(\?|$|\/)/);
  await expect(page.locator('[data-theme="privat"]').first()).toBeAttached();
  const accent = await page.locator('[data-theme="privat"]').first().evaluate((el) => getComputedStyle(el).getPropertyValue("--color-accent").trim());
  expect(accent.toUpperCase()).toBe("#C4461A");
  expect(await logoSvg(page), "samme logo-geometri i Privat og Erhverv").toBe(erhvervLogo);
  await noHorizontalScroll(page);
  await shot(page, info, "PC-BRAND-01", "privat-forside");
  expect((await context.cookies()).find((c) => c.name === "db_aud")?.value).toBe("privat");
  await page.goto("/");
  await expect(page).toHaveURL(/\/privat/);
  const tab2 = await context.newPage();
  await tab2.goto("/");
  await expect(tab2, "ny fane husker Privat").toHaveURL(/\/privat/);
  // Tilbage til Erhverv via vælgeren på Privat-siden, og valget huskes igen
  await page.getByRole("navigation", { name: "Vælg: virksomhed eller privat" }).first().getByRole("link", { name: /Erhverv/ }).click();
  await expect(page).toHaveURL(/erhverv|\/da\/?$|\/$/);
  await page.reload();
  expect((await context.cookies()).find((c) => c.name === "db_aud")?.value).toBe("erhverv");
  await tab2.goto("/");
  await expect(tab2).not.toHaveURL(/\/privat/);
});

test("PC-FUN-01: «Prøv gratis i 14 dage» → opret konto → bekræft e-mail → Stripe-checkout med kort; aldrig demo-Dag", async ({ page, context }, info) => {
  test.setTimeout(150_000);
  await context.setExtraHTTPHeaders({ "x-real-ip": uniqueIp() });
  await page.goto("/privat");
  await page.getByRole("link", { name: /Prøv gratis i 14 dage/ }).first().click();
  await expect(page.getByRole("heading", { name: /Opret privat konto/ })).toBeVisible({ timeout: 30_000 });
  expect(page.url(), "ingen mellemlanding på demo-Dag").not.toMatch(/\/privat\/dag/);
  await page.waitForTimeout(2000); // hydration
  await shot(page, info, "PC-FUN-01", "signup");
  const email = `qa-pk-fun01-${info.project.name}-${Date.now()}@example.com`;
  await page.getByLabel("Dit navn").fill("Mette Hansen");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill("Korrekt-Hest-Batteri-42");
  for (const c of await page.getByRole("checkbox").all()) await c.check().catch(() => {});
  await page.getByRole("button", { name: /^Opret/ }).click();
  await page.waitForURL(/\/privat\/konto/, { timeout: 30_000 });
  await page.waitForTimeout(2000);
  await shot(page, info, "PC-FUN-01", "efter-signup");
  const box = (await (await page.request.get("/api/backend/dev/mailbox")).json()) as { items: { body_text: string }[] };
  const link = box.items.map((m) => /(https?:\/\/\S*token=[\w-]+\S*)/.exec(m.body_text)?.[1]).find(Boolean);
  expect(link, "bekræftelsesmail").toBeTruthy();
  info.annotations.push({ type: "url-after-signup", description: page.url() }, { type: "verify-link", description: String(link) });
  await page.goto(link!.replace(/^https?:\/\/[^/]+/, ""));
  await page.waitForTimeout(4000);
  await shot(page, info, "PC-FUN-01", "efter-bekraeft");
  info.annotations.push({ type: "url-after-verify", description: page.url() });
  // F-PK-04: the next step after verifying must lead back to the Privat checkout, never into Erhverv onboarding.
  const next = page.getByRole("link", { name: /Fortsæt/ }).first();
  const href = (await next.count()) ? await next.getAttribute("href") : page.url();
  expect.soft(href ?? "", "efter bekræftelse: videre til Privat-checkout, ikke /onboarding/workspace").toMatch(/\/privat/);
  if (!(await page.locator("[data-testid=fake-stripe]").count())) {
    // Back to the plan the visitor chose (the page the e-mail link returns to, or Konto with the chosen plan)
    if (!/\/privat\/konto/.test(page.url())) await page.goto("/privat/konto?plan=plus&interval=month");
    await page.waitForTimeout(4000);
  }
  await shot(page, info, "PC-FUN-01", "checkout");
  await expect(page.locator("[data-testid=fake-stripe]"), "Stripe-checkout med navn, adresse, telefon og kort").toBeVisible({ timeout: 20_000 });
  for (const f of ["Navn på kortholder", "Adresse", "Telefon", "Kortnummer"]) await expect(page.getByLabel(f, { exact: true }), f).toBeVisible();
});
