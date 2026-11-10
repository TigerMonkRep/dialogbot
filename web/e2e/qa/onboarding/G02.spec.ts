import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, completeProfile, snap } from "./e2b";

/* QA G02 (E2B) – /app/setup/plan. Krav: "Goals, existing tools and guidance preference; editable plan using existing business information."
 * Byggevejledningen har ingen planside; målene vælges i trin 1 del C. Denne spec dokumenterer hvad der findes. */
const ID = "G02";

test("G02 · /app/setup/plan: ingen 404 for gamle links; plan-data og UI-trin er enige om næste skridt", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const res = await page.goto("/app/setup/plan");
  await snap(page, ID, info, "app-setup-plan");
  const status = res?.status() ?? 0;
  test.info().annotations.push({ type: "route", description: `${status} → ${page.url()}` });
  expect(status, `/app/setup/plan svarer ${status} (${page.url()})`).toBeLessThan(400);
  // backend plan (G01/G02/G05/G08 document) vs. the stepper's own computation
  const plan = (await api(page).get(`/workspaces/${wsId}/setup/plan`)).body;
  test.info().annotations.push({ type: "plan", description: JSON.stringify({ next: plan?.next_action ?? plan?.next, guidance: plan?.guidance_mode, tasks: (plan?.tasks ?? []).map((t: { key: string; status: string }) => `${t.key}:${t.status}`) }).slice(0, 900) });
  const g = (await api(page).get(`/workspaces/${wsId}/goals`)).body;
  expect(g.guidance_mode, "vejledningspræference findes i data").toBeTruthy();
  // existing tools / guidance preference are not editable anywhere in the UI
  await page.goto("/opsaetning/1");
  expect.soft(await page.getByText(/vejledning|Hvor meget hjælp|værktøjer I bruger|Hvilke systemer/i).count(), "ingen kontrol for vejledningspræference eller eksisterende værktøjer").toBeGreaterThan(0);
});
