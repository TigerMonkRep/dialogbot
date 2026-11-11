import { expect, test } from "@playwright/test";
import { evid, internalLinksOk, noHorizontalScroll, snap } from "./p1a-helpers";

/* QA P02 (e2e-erhverv A, wave 2): /reception – incoming calls, chat and requested callbacks; existing-number explanation;
 * reception setup CTA. Implementation: the reception page is /ai-receptionist (Danish route, web/src/app/ai-receptionist,
 * docs/site-pages.md); the handoff path /reception does not exist (404). */
const ID = "P02";
evid(ID);

test("P02 · /ai-receptionist dækker opkald, chat, tilbageringning, eget nummer og opsætnings-CTA", async ({ page }, info) => {
  const r = await page.goto("/ai-receptionist");
  expect(r?.status()).toBe(200);
  await expect(page).toHaveURL(/\/da\/ai-receptionist$/);
  await expect(page.locator("h1")).toHaveCount(1);
  const main = page.locator("main");
  await expect(main).toContainText(/tager imod opkald og chats/);                 // incoming calls + chat
  await expect(main).toContainText(/så I kan ringe tilbage/);                    // requested callbacks
  await expect(main).toContainText(/beholde jeres nuværende nummer og viderestille/); // existing number
  await expect(main.locator("a[href='/da/byggevejledning']").first()).toBeVisible();   // setup CTA
  await expect(main.locator("a[href='/da/proev']").first()).toBeVisible();
  // FAQ answers open
  await main.getByText("Kan jeg beholde mit telefonnummer?").click();
  await expect(main.getByText("Kan jeg beholde mit telefonnummer?").locator("xpath=ancestor::details[1]")).toHaveAttribute("open", "");
  await noHorizontalScroll(page);
  expect(await internalLinksOk(page)).toEqual([]);
  await snap(page, info, ID, "ai-receptionist");
});

test("P02 · branchesider findes for alle seks brancher og har samme opbygning", async ({ page }) => {
  for (const b of ["haandvaerkere", "klinikker", "frisoerer", "autovaerksteder", "raadgivere", "restauranter"]) {
    const r = await page.goto(`/da/ai-receptionist/${b}`);
    expect(r?.status(), b).toBe(200);
    await expect(page.locator("h1"), b).toHaveCount(1);
    await expect(page.locator("main a[href='/da/proev']").first(), b).toBeVisible();
  }
  expect((await page.goto("/da/ai-receptionist/findes-ikke"))?.status()).toBe(404);
});

test("P02 · den viderestillings-guide, siden lover, findes og forklarer at slå det fra igen", async ({ page }) => {
  await page.goto("/da/viden/viderestil-telefonen");
  await expect(page.locator("h1")).toContainText(/viderestiller/i);
  await expect(page.locator("main")).toContainText("Slå al viderestilling fra: ##002#");
});
