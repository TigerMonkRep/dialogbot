import { expect, test } from "@playwright/test";
import { evid, internalLinksOk, noHorizontalScroll, snap, unlock } from "./p1a-helpers";

/* QA P04 (e2e-erhverv A, wave 2): /how-it-works – business knowledge, review, testing, activation and ongoing control;
 * multiple industries; DB-006: no unsupported certification/hosting/free/SLA/extra-minute claims. Implementation: the
 * «Sådan virker det» content is /byggevejledning (preview-gated) plus the #saadan section of /erhverv. */
const ID = "P04";
evid(ID);
const UNSUPPORTED = /\bISO[ -]?\d|\bSLA\b|99[,.]9 ?%|certificer|ISAE|garanti for oppetid|oppetidsgaranti/i;

test.beforeEach(async ({ page }) => { await unlock(page); });

test("P04 · byggevejledningen viser viden → test → aktivering → løbende kontrol", async ({ page }, info) => {
  const r = await page.goto("/da/byggevejledning");
  expect(r?.status()).toBe(200);
  const main = page.locator("main");
  await expect(main).toContainText("Fortæl os om din virksomhed");      // business knowledge
  await expect(main).toContainText(/prøveopkald/);                      // testing
  await expect(main).toContainText(/Tænd/);                             // activation
  await expect(main).toContainText(/altid rette, hvad Dialogbot må sige/); // ongoing control
  await noHorizontalScroll(page);
  expect(await internalLinksOk(page)).toEqual([]);
  await snap(page, info, ID, "byggevejledning");
});

test("P04 · godkendelse (review) og flere brancher på Erhverv-siden", async ({ page }) => {
  await page.goto("/da/erhverv");
  await expect(page.locator("main")).toContainText(/viden I selv har godkendt/);
  await expect(page.locator("main")).toContainText(/«Godkend\?»/);
  for (const b of ["Håndværkere", "Klinikker", "Frisører og saloner", "Autoværksteder", "Rådgivere og kontorer"]) {
    await expect(page.getByRole("link", { name: b }).first()).toBeAttached();
  }
});

test("P04 · DB-006: ingen udokumenterede certificerings-, SLA- eller oppetidsløfter på de offentlige sider", async ({ page }) => {
  for (const p of ["/da", "/da/erhverv", "/da/byggevejledning", "/da/priser", "/da/kontakt", "/da/ai-receptionist", "/da/gdpr", "/da/om"]) {
    await page.goto(p);
    const text = await page.locator("body").innerText();
    expect(text.match(UNSUPPORTED)?.[0] ?? null, p).toBeNull();
  }
});
