import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, completeProfile, setGoals, snap } from "./e2b";

/* QA G05 (E2B) – /app/setup/readiness → the next step; Betaling «Mangler: …» (blokerende) + webchat-krav.
 * Since 12/11 (Fürster): the chat is set up in its own step and goes live only with a paid subscription.
 * Krav: "Goal-specific checks, test evidence/time/scope, blocking versus optional tasks and exact fix links."
 * Kilde: web/src/app/opsaetning/_parts/channels.tsx (ChatSetup, GoLive); app/modules/setup/checks.py. */
const ID = "G05";

test("G05 · /app/setup/readiness viderestiller; telefon-mål: blokerende mangler + abonnementet i Betaling", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  await page.goto("/app/setup/readiness");
  await expect(page).toHaveURL(/\/opsaetning\/viden$/);
  await page.goto("/opsaetning/betaling");
  await expect(page.getByText(/Mangler: bekræft jeres nummer/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Gå live" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Bekræft abonnement" })).toBeVisible();
  await snap(page, ID, info, "telefon-mangler");
});

test("G05 · webchat-mål uden hjemmeside: præcise links til at rette det, og ingen «tænd» før abonnementet", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId, { website_url: null, manual_setup: true });
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false });
  await page.goto("/opsaetning/chat");
  await expect(page.getByLabel("Jeres hjemmeside (domæne)")).toHaveValue("");
  await expect(page.getByText("Skriv jeres hjemmesides adresse – chatten må kun vises dér.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Godkend mindst én ting under Viden/ })).toHaveAttribute("href", "/opsaetning/viden");
  await expect(page.getByRole("button", { name: "Tænd webchatten" })).toHaveCount(0);
  await expect(page.getByText("Chatten går live, når abonnementet er på plads")).toBeVisible();
  await snap(page, ID, info, "webchat-uden-side");
});

test("G05 · webchat tændes efter betaling (ét klik, dobbeltklik giver én version) og tjekket er ærligt om «ikke set på siden endnu»", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId, { website_url: "https://fjordgulv.example", manual_setup: false });
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false });
  expect((await api(page).send("POST", `/workspaces/${wsId}/agreement`, { model: "A" })).status).toBeLessThan(300);
  await page.goto("/opsaetning/chat");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  // 1) no approved knowledge yet: it says why and how to fix it, and cannot be switched on
  await expect(page.getByRole("link", { name: /Godkend mindst én ting under Viden/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tænd webchatten" })).toBeDisabled();
  await snap(page, ID, info, "webchat-mangler-viden");
  // 2) add an approved fact (as Virksomhed would) and turn on – double click
  const it = (await api(page).send("POST", `/workspaces/${wsId}/knowledge/items`, { kind: "opening_hours", title: "Åbningstider", content: { weekly: [{ days: ["mon", "tue", "wed", "thu", "fri"], open: "08:00", close: "16:00" }] } })).body;
  expect((await api(page).send("POST", `/workspaces/${wsId}/knowledge/versions/${it.open_draft.id}/approve`)).status).toBe(200);
  await page.reload();
  const v0 = (await api(page).get(`/workspaces/${wsId}/webchat`)).body.version;
  await page.getByRole("button", { name: "Tænd webchatten" }).dblclick();
  await expect(page.getByText("Chatten er live og svarer besøgende på hjemmesiden.")).toBeVisible();
  const w = (await api(page).get(`/workspaces/${wsId}/webchat`)).body;
  expect(w.enabled).toBe(true);
  expect(w.allowed_origins).toEqual(["https://fjordgulv.example"]);
  expect(w.version - v0, "dobbeltklik gav mere end én ændring").toBeLessThanOrEqual(1);
  await expect(page.getByText(/Når linjen er på siden, skifter status/)).toBeVisible();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await snap(page, ID, info, "webchat-taendt");
});
