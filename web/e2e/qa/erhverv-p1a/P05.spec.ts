import { expect, test } from "@playwright/test";
import PRICES from "../../../src/lib/prices.json";
import { evid, noHorizontalScroll, snap } from "./p1a-helpers";

/* QA P05 (e2e-erhverv A, wave 2): /pricing – two alternative reception models, separate campaign volume, meaningful
 * units, example calculator. Implementation: /priser (web/src/app/priser/page.tsx) with ONE subscription and per-call
 * campaign pricing (since 11/11 model A': 4/1/0,25 kr. by outcome + 2 kr. per started minute after the package); there is no calculator and no Model A/B (docs/requirements-status.md:36 «intet endpoint»).
 * Per the wave brief the price LEVEL is not judged here (it changes on another branch): we only prove the page is
 * internally consistent with its own source, web/src/lib/prices.json (generated from app/modules/billing/markets.py). */
const ID = "P05";
evid(ID);
const D = PRICES.erhverv.DKK;
const kr = (minor: number) => (minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 });

test("P05 · /priser viser tallene fra prices.json (prismodel A')", async ({ page }, info) => {
  const r = await page.goto("/da/priser");
  expect(r?.status()).toBe(200);
  const main = await page.locator("main").innerText();
  expect(main).toContain(`${kr(D.monthly)} kr.`);
  expect(main).toContain(`${PRICES.includedMinutes} minutter`);
  // A': per call by outcome after the package, plus every started minute
  for (const v of [D.call_answered, D.call_voicemail, D.call_no_answer, D.outbound_extra_minute, D.extra_minute, D.setup])
    expect(main, `pris ${v} øre mangler på /priser`).toContain(`${kr(v)} kr.`);
  expect(main).toMatch(/påbegyndt/);
  await noHorizontalScroll(page);
  await snap(page, info, ID, "priser");
});

test("P05 · Erhverv-landingens priser bruger samme enhedspriser som /priser", async ({ page }) => {
  await (await import("./p1a-helpers")).unlock(page);
  await page.goto("/da/erhverv");
  const main = await page.locator("main").innerText();
  expect(main).toContain(`${kr(D.monthly)} kr.`);
  for (const v of [D.call_answered, D.outbound_extra_minute]) expect(main).toContain(`${kr(v)} kr.`);
});

test("P05 · andre markeder: /en/priser bruger EUR-tallene fra samme kilde", async ({ page }) => {
  await page.goto("/en/priser");
  const main = await page.locator("main").innerText();
  const E = PRICES.erhverv.EUR;
  expect(main).toMatch(new RegExp(`€\\s?${E.monthly / 100}|${E.monthly / 100}\\s?€|EUR\\s?${E.monthly / 100}`));
});

test("P05 · prisberegner og to receptionsmodeller (krav) – ikke bygget", async ({ page }) => {
  test.info().annotations.push({ type: "not-implemented", description: "Ingen beregner og ingen Model A/B på /priser; ét abonnement + pr.-opkald-kampagner." });
  await page.goto("/da/priser");
  await expect(page.locator("main input[type=number], main input[type=range], main [data-calculator]")).toHaveCount(0);
});
