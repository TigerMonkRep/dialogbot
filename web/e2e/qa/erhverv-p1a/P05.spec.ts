import { expect, test } from "@playwright/test";
import PRICES from "../../../src/lib/prices.json";
import { evid, noHorizontalScroll, snap } from "./p1a-helpers";

/* QA P05 (e2e-erhverv A, wave 2): /pricing – two alternative reception models, separate campaign volume, meaningful
 * units, example calculator. Implementation: /priser (web/src/app/priser/page.tsx) with ONE subscription and per-call
 * campaign pricing; there is no calculator and no Model A/B (docs/requirements-status.md:36 «intet endpoint»).
 * Per the wave brief the price LEVEL is not judged here (it changes on another branch): we only prove the page is
 * internally consistent with its own source, web/src/lib/prices.json (generated from app/modules/billing/markets.py). */
const ID = "P05";
evid(ID);
const D = PRICES.erhverv.DKK;
const kr = (minor: number) => (minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 });

test("P05 · /priser viser tallene fra prices.json, og de regnede eksempler stemmer med enhedspriserne", async ({ page }, info) => {
  const r = await page.goto("/da/priser");
  expect(r?.status()).toBe(200);
  const main = await page.locator("main").innerText();
  expect(main).toContain(`${kr(D.monthly)} kr. om måneden`);
  expect(main).toContain(`${PRICES.inboundIncludedMinutes} minutters indgående opkald`);
  expect(main).toContain(`${kr(D.call)} kr. pr. udgående opkald plus ${kr(D.minute)} kr. pr. påbegyndt samtaleminut`);
  expect(main).toContain(`derudover ${kr(D.extra_minute)} kr.`);
  expect(main).toContain(`${kr(D.setup)} kr.`);
  // worked examples on the page: unanswered = one call; 3 minutes = call + 3 × minute
  expect(main).toContain(`Et ubesvaret opkald koster derfor ${kr(D.call)} kr.`);
  expect(main).toContain(`en samtale på 3 minutter ${kr(D.call + 3 * D.minute)} kr.`);
  await noHorizontalScroll(page);
  await snap(page, info, ID, "priser");
});

test("P05 · Erhverv-landingens eksempler bruger samme enhedspriser som /priser", async ({ page }) => {
  await (await import("./p1a-helpers")).unlock(page);
  await page.goto("/da/erhverv");
  const main = await page.locator("main").innerText();
  expect(main).toContain(`Ubesvaret: ${kr(D.call)} kr. Tre minutters samtale: ${kr(D.call + 3 * D.minute)} kr.`);
  expect(main).toContain(`${kr(D.call)} kr. pr. opkald + ${kr(D.minute)} kr. pr. minut`);
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
