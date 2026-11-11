import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, completeProfile, setGoals, snap } from "./e2b";

/* QA G05 (E2B) – /app/setup/readiness → trin 3 «Mangler: …» (blokerende) + webchat-krav.
 * Krav: "Goal-specific checks, test evidence/time/scope, blocking versus optional tasks and exact fix links."
 * Kilde: web/src/app/opsaetning/3/step3.tsx:310-318,347; app/modules/setup/checks.py. */
const ID = "G05";

test("G05 · /app/setup/readiness viderestiller; telefon-mål: blokerende mangler + link til abonnement", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  await page.goto("/app/setup/readiness");
  await expect(page).toHaveURL(/\/opsaetning\/3$/);
  await expect(page.getByText(/Mangler: bekræft jeres nummer/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toBeDisabled();
  const sub = page.getByRole("link", { name: "Bekræft abonnement" });
  if (await sub.count()) {
    await sub.click();
    await expect(page).toHaveURL(/\/app\/konto/);
  }
  await snap(page, ID, info, "telefon-mangler");
});

test("G05 · webchat-mål uden hjemmeside: knappen er slukket OG der er et præcist link til at rette det", async ({ page }, info) => {
  test.fail(true, "F-E2B-12-G05: S2 new – «Tænd webchatten» i trin 3 afvises med «Widgetten kan ikke slås til endnu» uden grund og uden …");
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId, { website_url: null, manual_setup: true });
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false });
  await page.goto("/opsaetning/3");
  await expect(page.getByRole("button", { name: "Tænd webchatten" })).toBeDisabled();
  await expect(page.getByText(/Mangler: tænd webchatten/)).toBeVisible();
  await snap(page, ID, info, "webchat-uden-side");
  const fix = await page.locator("main").getByRole("link", { name: /trin 1|hjemmeside|Ret/i }).count();
  expect.soft(fix, "ingen link til at tilføje hjemmesiden, som webchat kræver").toBeGreaterThan(0);
});

test("G05 · webchat tændes (ét klik, dobbeltklik giver én version) og tjekket er ærligt om «ikke set på siden endnu»", async ({ page }, info) => {
  test.fail(true, "F-E2B-12-G05: S2 new – «Tænd webchatten» i trin 3 afvises med «Widgetten kan ikke slås til endnu» uden grund og uden …");
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId, { website_url: "https://fjordgulv.example", manual_setup: false });
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false });
  await page.goto("/opsaetning/3");
  // 1) no approved knowledge yet: the refusal must say why and how to fix it
  await page.getByRole("button", { name: "Tænd webchatten" }).click();
  const refusal = page.locator("main").getByRole("alert").filter({ hasText: /kan ikke slås til/ });
  await expect(refusal).toBeVisible();
  await snap(page, ID, info, "webchat-afvist-uden-grund");
  const why = await refusal.innerText();
  expect.soft(why, "afvisningen siger ikke hvorfor (ingen godkendt viden) eller hvad man skal gøre").toMatch(/viden|åbningstider|godkend/i);
  // 2) add an approved fact (as trin 1 would) and turn on – double click
  const it = (await api(page).send("POST", `/workspaces/${wsId}/knowledge/items`, { kind: "opening_hours", title: "Åbningstider", content: { weekly: [{ days: ["mon", "tue", "wed", "thu", "fri"], open: "08:00", close: "16:00" }] } })).body;
  expect((await api(page).send("POST", `/workspaces/${wsId}/knowledge/versions/${it.open_draft.id}/approve`)).status).toBe(200);
  await page.reload();
  const v0 = (await api(page).get(`/workspaces/${wsId}/webchat`)).body.version;
  await page.getByRole("button", { name: "Tænd webchatten" }).dblclick();
  await expect(page.locator("pre")).toBeVisible();
  const w = (await api(page).get(`/workspaces/${wsId}/webchat`)).body;
  expect(w.enabled).toBe(true);
  expect(w.allowed_origins).toEqual(["https://fjordgulv.example"]);
  expect(w.version - v0, "dobbeltklik gav mere end én ændring").toBeLessThanOrEqual(1);
  await expect(page.getByText(/Når linjen er på siden, skifter status/)).toBeVisible();
  await expect(page.getByText("Tændt", { exact: true })).toBeVisible();
  await snap(page, ID, info, "webchat-taendt");
});
