import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, completeProfile, setGoals, snap } from "./e2b";

/* QA O03 (E2B) – /onboarding/goals → trin 1 del C «Hvad skal den gøre for jer?».
 * Krav: "Conversation goals, proposed questions, intent branches and owner editing."
 * Kilde: web/src/app/opsaetning/1/step1.tsx:222,283-303, web/src/lib/setup.ts goalsFromCards. */
const ID = "O03";
const card = (page: import("@playwright/test").Page, name: RegExp) => page.getByRole("checkbox", { name });

test("O03 · kortene gemmes som mål (hurtige klik, reload) og styrer hvilket trin der er næste", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await page.goto("/opsaetning/1");
  // fresh reception workspace: what is pre-selected must match the stored goals
  const g0 = (await api(page).get(`/workspaces/${wsId}/goals`)).body;
  await expect(card(page, /Tage telefonen/)).toBeChecked({ checked: g0.inbound_phone });
  // four quick clicks inside the save pause – the last state must win
  for (const n of [/Booke aftaler/, /Svare på hjemmesiden/, /Ringe kunder op/]) await card(page, n).click();
  await card(page, /Svare på hjemmesiden/).click();
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  const want = { booking: !g0.booking, webchat: g0.webchat, product_intent: "both" };
  await expect.poll(async () => { const g = (await api(page).get(`/workspaces/${wsId}/goals`)).body; return { booking: g.booking, webchat: g.webchat, product_intent: g.product_intent }; }).toEqual(want);
  await expect(page.getByRole("button", { name: /Videre til trin 2/ })).toBeVisible();
  await page.reload();
  await expect(card(page, /Booke aftaler/)).toBeChecked({ checked: want.booking });
  await expect(card(page, /Ringe kunder op/)).toBeChecked();
  await snap(page, ID, info, "kort");

  // campaigns only: reception channels are switched off in the stored goals
  for (const n of [/Tage telefonen/, /Booke aftaler/, /Svare på hjemmesiden/]) if (await card(page, n).isChecked()) await card(page, n).click();
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await expect.poll(async () => (await api(page).get(`/workspaces/${wsId}/goals`)).body).toMatchObject({ product_intent: "campaigns", inbound_phone: false, webchat: false, booking: false, callback: false });
});

test("O03 · læser kan ikke ændre mål (UI og API)", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const r = await colleague(page, browser, info, wsId, "reader");
  await r.page.goto("/opsaetning/1");
  await expect(card(r.page, /Booke aftaler/)).toBeDisabled();
  const g = (await api(r.page).get(`/workspaces/${wsId}/goals`)).body;
  expect((await api(r.page).send("PUT", `/workspaces/${wsId}/goals`, { ...g, booking: !g.booking, expected_version: g.version })).status).toBe(403);
  await r.ctx.close();
});

test("O03 · krav: samtalemål, foreslåede spørgsmål og intent-grene kan ses og redigeres af ejeren", async ({ page }, info) => {
  test.fail(true, "O03: not-implemented – samtalemål, foreslåede spørgsmål og intent-grene");
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  // The backend can suggest goals (POST …/goals/suggestions). Is any of it visible to the owner anywhere in the setup?
  const sugg = await api(page).send("POST", `/workspaces/${wsId}/goals/suggestions`);
  test.info().annotations.push({ type: "api", description: `suggestions ${sugg.status}: ${JSON.stringify(sugg.body).slice(0, 200)}` });
  const found: string[] = [];
  for (const path of ["/opsaetning/1", "/opsaetning/3", "/app/indstillinger"]) {
    await page.goto(path);
    if (await page.getByText(/Samtalemål|samtalens mål|Spørgsmål den stiller|Det spørger den om/i).count()) found.push(path);
  }
  await snap(page, ID, info, "indstillinger");
  expect.soft(found, "ingen side viser/redigerer samtalemål, foreslåede spørgsmål eller intent-grene").not.toEqual([]);
});

test("O03 · «Alle indstillinger» viser kampagne-valget fra trin 1 (product_intent – ikke callback)", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const tile = () => page.locator("main").locator("li, a, button, div").filter({ hasText: /^Udgående opkald/ }).last();
  // Reception with phone + callback, «Ringe kunder op» NOT chosen.
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  await page.goto("/app/indstillinger");
  await snap(page, ID, info, "indstillinger-kun-reception");
  const recText = await tile().innerText();
  // Campaigns only (the card «Ringe kunder op»): no callback.
  await setGoals(page, wsId, { product_intent: "campaigns", inbound_phone: false, webchat: false, callback: false, booking: false });
  await page.reload();
  await snap(page, ID, info, "indstillinger-kun-kampagner");
  const campText = await tile().innerText();
  expect.soft(recText, "kun reception valgt, men kampagner står som «Valgt»").toContain("Ikke valgt");
  expect(campText, "kun kampagner valgt, men kampagner står som «Ikke valgt»").not.toContain("Ikke valgt");
});
