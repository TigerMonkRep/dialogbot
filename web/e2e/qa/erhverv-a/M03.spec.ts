import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";

/* QA M03 (e2e-erhverv A): /admin/operations (→ /app/operator/admin/drift) – job/delivery/call/booking-sync status,
 * dependency incidents, controlled retry, suspension; no duplicate calls/bookings. DB-007: no timer-simulated recovery. */
const EVID = "../qa/evidence/M03";
const CSRF = { "x-requested-with": "dialogbot" };

test("M03 · kunden ser ikke drift; operatøren ser database, kø, fejlede opgaver og mails – ingen simuleret genopretning", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  await page.goto("/app/operator/admin/drift");
  await expect(page.getByText("Admin er kun for Dialogbot-operatører.")).toBeVisible();
  expect((await page.request.get("/api/backend/operator/admin/operations")).status()).toBe(403);
  await page.context().clearCookies();

  await freshOwner(page, info);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin/drift");
  for (const h of ["Database og kode", "Opgavekø (7 dage)", "Fejlede opgaver", "Seneste e-mails", "Logbog (seneste 40)"]) {
    await expect(page.getByRole("heading", { name: h })).toBeVisible();
  }
  await expect(page.getByText("Samme version")).toBeVisible();
  // DB-007: nothing on the page changes by itself (no timer-driven "recovered" state)
  const before = await page.locator("main").innerText();
  await page.waitForTimeout(4000);
  expect(await page.locator("main").innerText()).toBe(before);
  await page.screenshot({ path: `${EVID}/${info.project.name}-drift.png`, fullPage: true });
});

test("M03 · driftsskærmen viser opkald, kalender-synk, kontrolleret genkørsel og suspendering", async ({ page }, info) => {
  await freshOwner(page, info);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin/drift");
  await expect(page.getByRole("heading", { name: "Fejlede opgaver" })).toBeVisible();
  // M03 asks for call / booking-sync status, dependency incidents, controlled retry and suspension
  const text = (await page.locator("main").innerText()).toLowerCase();
  const missing = [["opkald", /opkald/], ["booking/kalender-synk", /synk|kalender|booking/], ["genkør/prøv igen", /genkør|prøv igen|retry/], ["suspendering", /suspend|pause/]]
    .filter(([, re]) => !(re as RegExp).test(text)).map(([n]) => n);
  info.annotations.push({ type: "missing", description: missing.join(", ") });
  expect(missing, "not implemented on the operations screen").toEqual([]);
});

test("M03 · operatøren sætter en kunde på pause og genoptager – kun operatører, og det står i logbogen", async ({ page }, info) => {
  // A customer cannot suspend anyone (also not their own workspace)
  const owner = await freshOwner(page, info);
  const denied = await page.request.post(`/api/backend/operator/admin/operations/workspaces/${owner.wsId}/suspend`, { headers: CSRF, data: { reason: "forsøg fra kunde" } });
  expect(denied.status()).toBe(403);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  const s = await page.request.post(`/api/backend/operator/admin/operations/workspaces/${owner.wsId}/suspend`, { headers: CSRF, data: { reason: "E2E: kalenderudbyder svarer 401" } });
  expect(s.ok()).toBeTruthy();
  const wsName = (await s.json()).workspace_name as string;
  // idempotent: a second suspend keeps the first reason
  expect((await (await page.request.post(`/api/backend/operator/admin/operations/workspaces/${owner.wsId}/suspend`, { headers: CSRF, data: { reason: "igen" } })).json()).reason).toBe("E2E: kalenderudbyder svarer 401");
  await page.goto("/app/operator/admin/drift");
  const section = page.getByRole("region", { name: "Suspendering (kunder sat på pause)" });
  const row = section.getByRole("listitem").filter({ hasText: wsName });
  await expect(row.getByText("E2E: kalenderudbyder svarer 401")).toBeVisible();
  for (const h of ["Afhængigheder og hændelser", "Opkald", "Kalender-synk (bookinger)"]) await expect(page.getByRole("heading", { name: h, exact: true })).toBeVisible();
  await page.screenshot({ path: `${EVID}/${info.project.name}-pause.png`, fullPage: true });
  const resume = section.getByRole("button", { name: `Genoptag ${wsName}`, exact: true });
  await resume.click();
  await expect(row).toHaveCount(0);
  const ops = await (await page.request.get("/api/backend/operator/admin/operations")).json();
  expect(ops.suspended.find((x: { workspace_id: string }) => x.workspace_id === owner.wsId)).toBeUndefined();
  const actions = ops.audit.filter((a: { workspace_id: string | null }) => a.workspace_id === owner.wsId).map((a: { action: string }) => a.action);
  expect(actions).toEqual(expect.arrayContaining(["operator.ops.workspace_suspended", "operator.ops.workspace_resumed"]));
  expect(actions.filter((a: string) => a === "operator.ops.workspace_suspended")).toHaveLength(1);
  // no horizontal overflow at either viewport
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
