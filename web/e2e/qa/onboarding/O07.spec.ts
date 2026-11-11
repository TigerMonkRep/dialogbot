import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, completeProfile, noStaging, setGoals, snap } from "./e2b";

/* QA O07 (E2B) – /onboarding/activation → trin 3 «Test & tænd» + /app?taendt=1.
 * Krav: "Readiness summary and personalised plan; link G01/G05, selected offer and next steps; reception to relevant channel
 * setup, campaigns to creation, booking customers to calendar setup."
 * Kilde: web/src/app/opsaetning/3/step3.tsx:300-351, web/src/lib/setup.server.ts, web/src/app/app/(admin)/page.tsx:39,59. */
const ID = "O07";

test("O07 · booking-kunde ledes til kalender (trin 2); telefon-kunde får telefon-opsætning og en ærlig mangelliste", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: true });
  await page.goto("/app/setup");
  await expect(page).toHaveURL(/\/opsaetning\/2$/);
  await expect(page.getByRole("heading", { name: "Hvor skal aftalerne lande?" })).toBeVisible();
  await setGoals(page, wsId, { booking: false });
  await page.goto("/app/setup");
  await expect(page).toHaveURL(/\/opsaetning\/3$/);
  await expect(page.getByRole("heading", { name: "Telefon", exact: true }).first()).toBeVisible();
  await expect(page.getByText("Næsten klar")).toBeVisible();
  await expect(page.getByText(/Mangler: bekræft jeres nummer/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toBeDisabled();
  await noStaging(page);
  await snap(page, ID, info, "telefon-mangler");
});

test("O07 · kun kampagner: må ikke få at vide at Dialogbot «tager telefonen», og skal ledes til at oprette en kampagne", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info, "campaigns");
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "campaigns", inbound_phone: false, webchat: false, callback: false, booking: false });
  await page.goto("/opsaetning/3");
  await snap(page, ID, info, "kun-kampagner-trin3");
  const turnOn = page.getByRole("button", { name: "Tænd Dialogbot" });
  const hasCampaignLink = await page.locator("main").getByRole("link", { name: /kampagne/i }).count();
  if (await turnOn.isVisible()) {
    await turnOn.click();
    await page.waitForURL(/\/app/);
  }
  await page.waitForTimeout(800);
  await snap(page, ID, info, "kun-kampagner-efter-taend");
  const body = await page.locator("main").innerText();
  const tel = (await api(page).get(`/workspaces/${wsId}/telephony`)).body;
  test.info().annotations.push({ type: "state", description: `url=${page.url()} telephony=${tel?.status?.code} campaignLink=${hasCampaignLink}` });
  expect.soft(hasCampaignLink, "trin 3 viser ingen vej til at oprette en kampagne").toBeGreaterThan(0);
  expect(body, `kampagne-kunde uden telefon får at vide «Den tager telefonen…» (telefoni: ${tel?.status?.code})`).not.toContain("Den tager telefonen, næste gang kunderne ringer.");
});

test("O07 · intet valgt i trin 1: «Tænd» må ikke love noget, der ikke er sat op", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: false, webchat: false, callback: false, booking: false });
  await page.goto("/opsaetning/3");
  await expect(page.getByText(/I valgte ikke at tage telefonen/)).toBeVisible();
  // F-E2B-03 (rettet i 1b96c6e): intet at tænde → ingen «Tænd»/«Alt er klar», men en vej tilbage til trin 1
  await expect(page.getByRole("heading", { name: "Vælg hvad Dialogbot skal gøre" })).toBeVisible();
  await snap(page, ID, info, "intet-valgt");
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toHaveCount(0);
  const main = await page.locator("main").innerText();
  expect(main).not.toContain("Alt er klar – tænd Dialogbot");
  expect(main, "intet er valgt, men siden siger at Dialogbot er tændt og tager telefonen").not.toContain("Den tager telefonen, næste gang kunderne ringer.");
  const back = page.locator("main").getByRole("link", { name: "Ret valget" }).last();
  await expect(back).toHaveAttribute("href", "/opsaetning/1");
  await back.click();
  await page.waitForURL(/\/opsaetning\/1/);
  await snap(page, ID, info, "intet-valgt-efter");
  // og I dag lover heller ikke noget
  await page.goto("/app?taendt=1");
  expect(await page.locator("main").innerText()).not.toContain("Den tager telefonen, næste gang kunderne ringer.");
});

test("O07 · læser i trin 3 må ikke se «Alt er klar», når telefonen ikke er sat op", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  const r = await colleague(page, browser, info, wsId, "reader");
  await r.page.goto("/opsaetning/3");
  await snap(r.page, ID, info, "laeser-trin3-indlaest");
  await expect(r.page.getByRole("heading", { name: "This page couldn’t load" }), "trin 3 crasher for en læser").toHaveCount(0);
  await expect(r.page.getByText("Kun ejere og administratorer kan tænde.")).toBeVisible();
  await snap(r.page, ID, info, "laeser-trin3");
  const txt = await r.page.locator("main").innerText();
  await r.ctx.close();
  expect.soft(txt, "læseren får at vide at telefonen ikke er valgt").not.toContain("I valgte ikke at tage telefonen");
  expect(txt, "læseren ser «Alt er klar», selvom intet er sat op").not.toContain("Alt er klar – tænd Dialogbot");
});
