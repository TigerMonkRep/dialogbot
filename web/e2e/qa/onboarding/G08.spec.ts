import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, completeProfile, snap } from "./e2b";

/* QA G08 (E2B) – /app/setup/next. Krav: "First real results, review prompts, optional improvements and re-opened checks after changes." */
const ID = "G08";

test("G08 · /app/setup/next og genåbnede tjek efter ændring", async ({ page }, info) => {
  test.fail(true, "F-E2B-14-G02: S3 new – Kravruterne /app/setup/plan, /app/setup/tasks/:id, /app/setup/team og /app/setup/next giver 404, …");
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const res = await page.goto("/app/setup/next");
  await snap(page, ID, info, "app-setup-next");
  test.info().annotations.push({ type: "route", description: `${res?.status()} → ${page.url()}` });
  const plan = (await api(page).get(`/workspaces/${wsId}/setup/plan`)).body;
  test.info().annotations.push({ type: "checks", description: JSON.stringify((plan?.checks ?? []).map((c: { key: string; status: string }) => `${c.key}:${c.status}`)).slice(0, 600) });
  expect.soft(res?.status() ?? 0, `/app/setup/next svarer ${res?.status()}`).toBeLessThan(400);
});
