import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";

/* QA H01 (e2e-erhverv A): /app/help and /app/support/:ticket – contextual help, support request with attachments,
 * status and thread. Sources: web/src/app/app/(admin)/hjaelp/page.tsx, web/src/app/app/(admin)/support/**,
 * app/modules/support/router.py; next.config.ts MOVED (/app/help → /app/hjaelp). */
const EVID = "../qa/evidence/H01";
const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(256)]);

test("H01 · hjælpen findes, alle «Gå dertil»-links virker, og der lyves ikke om support", async ({ page }, info) => {
  await login(page, SEEDED.staff);
  await page.goto("/app/help");
  await expect(page).toHaveURL(/\/app\/hjaelp$/);
  await expect(page.getByRole("heading", { level: 1, name: "Sådan bruger I Dialogbot" })).toBeVisible();
  const hrefs = [...new Set(await page.getByRole("link", { name: "Gå dertil" }).evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).getAttribute("href")!)))];
  expect(hrefs.length).toBeGreaterThan(5);
  for (const h of hrefs) {
    const r = await page.request.get(h);
    expect(r.status(), `help link ${h}`).toBeLessThan(400);
  }
  expect(await page.locator("body").innerText()).not.toMatch(/staging/i);
  // No invented SLA: the support card and page promise no response time.
  await expect(page.getByRole("link", { name: "Gå til support" })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toMatch(/\bSLA\b|[Ii]nden for \d+ (timer|minutter)/);
  await page.screenshot({ path: `${EVID}/${info.project.name}-hjaelp.png`, fullPage: true });
});

test("H01 · supportsag med vedhæftning, status og tråd (/app/support/:ticket)", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/hjaelp");
  await page.getByRole("link", { name: "Gå til support" }).click();
  await expect(page).toHaveURL(/\/app\/support\?fra=/);
  await expect(page.getByRole("heading", { level: 1, name: "Support" })).toBeVisible();
  await expect(page.getByText("Ingen sager endnu.")).toBeVisible();
  const subject = `Kalenderen viser ikke aftaler ${info.project.name}`;
  await page.getByLabel("Emne").fill(subject);
  await page.getByLabel("Kategori").selectOption("calendar");
  await page.getByLabel("Beskrivelse").fill("Bookinger fejler siden i går aftes. Skærmbillede vedhæftet.");
  await page.locator("#support-new-files").setInputFiles({ name: "skaermbillede.png", mimeType: "image/png", buffer: PNG });
  await page.getByRole("button", { name: "Opret sag" }).click();

  await expect(page).toHaveURL(/\/app\/support\/1$/);
  const r = await page.request.get("/app/support/1");
  expect(r.status(), "support ticket page must exist").toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: subject })).toBeVisible();
  await expect(page.locator("[data-status]").first()).toHaveText(/Hos Dialogbot/i);
  await expect(page.getByText("Sagen ligger hos Dialogbot support.")).toBeVisible();
  const att = page.getByRole("link", { name: /skaermbillede\.png/ });
  await expect(att).toBeVisible();
  const dl = await page.request.get((await att.getAttribute("href"))!);
  expect(dl.status()).toBe(200);
  expect(dl.headers()["content-disposition"]).toMatch(/^attachment;/);
  await page.screenshot({ path: `${EVID}/${info.project.name}-support-ticket.png`, fullPage: true });

  // thread: a reply appears; resolve and reopen change the status
  await page.getByLabel("Skriv et svar").fill("Det gælder også Mads' kalender.");
  await page.getByRole("button", { name: "Send svar" }).click();
  await expect(page.getByText("Det gælder også Mads' kalender.")).toBeVisible();
  await page.getByRole("button", { name: "Markér som løst" }).click();
  await expect(page.locator("[data-status]").first()).toHaveText(/Løst/i);
  await page.getByRole("button", { name: "Genåbn sag" }).click();
  await expect(page.locator("[data-status]").first()).toHaveText(/Hos Dialogbot/i);

  // the list shows it; an unknown number is «findes ikke»
  await page.goto("/app/support");
  await expect(page.getByRole("link", { name: new RegExp(subject) })).toBeVisible();
  expect((await page.request.get("/app/support/999")).status()).toBe(404);
  await page.screenshot({ path: `${EVID}/${info.project.name}-support-liste.png`, fullPage: true });
});

test("H01 · en læser ser hjælpen, men ikke supportsagerne", async ({ page }) => {
  await login(page, SEEDED.reader);
  await page.goto("/app/support");
  await expect(page.getByText("Supportsager kan ses og oprettes af medarbejdere, administratorer og ejere.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Opret sag" })).toHaveCount(0);
});
