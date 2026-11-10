import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, snap } from "./e2b";

/* QA G07 (E2B) – /app/setup/team. Krav: "Setup task ownership/assignment, permission-aware colleague handoff and existing invitation flow."
 * Kilde: app/modules/setup/router.py:89 (PUT …/tasks/{key}/assignee). */
const ID = "G07";

test("G07 · API: ejer tildeler opgave; medarbejder kan kun tage den selv; læser afvises; ikke-medlem afvises", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const staff = await colleague(page, browser, info, wsId, "staff");
  const reader = await colleague(page, browser, info, wsId, "reader");
  const me = async (p: typeof page) => (await api(p).get("/auth/me")).body.id as string;
  const staffId = await me(staff.page), readerId = await me(reader.page), ownerId = await me(page);
  const plan = (await api(page).get(`/workspaces/${wsId}/setup/plan`)).body;
  const key = plan.tasks[0].key as string;
  const put = (p: typeof page, user_id: string | null) => api(p).send("PUT", `/workspaces/${wsId}/setup/tasks/${key}/assignee`, { user_id });
  expect((await put(page, staffId)).status).toBe(200);
  expect((await put(staff.page, ownerId)).status, "medarbejder må ikke tildele andre").toBe(403);
  expect((await put(staff.page, staffId)).status).toBe(200);
  expect((await put(reader.page, readerId)).status, "læser må ikke tage opgaver").toBe(403);
  expect((await put(page, "00000000-0000-0000-0000-000000000001")).status).toBe(422);
  await staff.ctx.close(); await reader.ctx.close();
});

test("G07 · UI: kan opsætningen gives videre til en kollega (tildel/inviter) fra byggevejledningen?", async ({ page }, info) => {
  test.fail(true, "F-E2B-14-G02: S3 new – Kravruterne /app/setup/plan, /app/setup/tasks/:id, /app/setup/team og /app/setup/next giver 404, …");
  await freshOwner(page, info);
  const res = await page.goto("/app/setup/team");
  test.info().annotations.push({ type: "route", description: `${res?.status()} → ${page.url()}` });
  await page.goto("/opsaetning/1");
  const handoff = await page.getByRole("button", { name: /kollega|Giv videre|Tildel|Inviter/i }).or(page.getByRole("link", { name: /kollega|Giv videre|Tildel|Inviter/i })).count();
  await snap(page, ID, info, "ingen-overdragelse");
  expect.soft(res?.status() ?? 0, "/app/setup/team").toBeLessThan(400);
  expect.soft(handoff, "ingen måde at give et trin videre til en kollega i opsætningen").toBeGreaterThan(0);
});
