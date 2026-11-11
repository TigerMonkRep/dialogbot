import { expect, test, type Page } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";

/* QA I01–I05 + R04/R05/X21 UI (voice-qa, wave 2). v2 maps /app/inbox, /app/leads, /app/tasks to «Opkald»
 * (/app/opkald, /app/opkald/henvendelser/:id) – see docs/kundeapp-v2.md and web/next.config.ts MOVED.
 * Data: a webchat conversation + «Bliv kontaktet» (lead + follow-up task) through the public widget API, exactly
 * like the chat frame does it. No call, no SMS, no network outside localhost. */
const CSRF = { "x-requested-with": "dialogbot" };
const EVID = "../qa/evidence";

async function seedChatLead(page: Page, wsId: string, who: string) {
  for (const [kind, title, content] of [["service", "Gulvafslibning", { price_net_minor: 14500 }]] as const) {
    const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind, title, content } })).json();
    await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
    expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  }
  const wc = await (await page.request.get(`/api/backend/workspaces/${wsId}/webchat`)).json();
  const w = await (await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: wc.version, enabled: true, allowed_origins: ["http://localhost:4199"], greeting: "" } })).json();
  const apiOrigin = new URL(w.embed_code.match(/src="([^"]+)"/)![1]).origin;
  // the stack serves the API on API_BASE_URL (:8200) while PUBLIC_BASE_URL (the frame origin the API expects) may differ
  const pub = `${process.env.API_BASE_URL ?? apiOrigin}/api/v1/public/webchat/${w.widget_key}`;
  const h = { origin: apiOrigin, "content-type": "application/json" };
  const conv = await (await page.request.post(`${pub}/conversations`, { headers: h, data: { host_origin: "http://localhost:4199" } })).json();
  expect((await page.request.post(`${pub}/conversations/${conv.conversation_id}/messages`, { headers: { ...h, "x-visitor-token": conv.visitor_token }, data: { text: "Kan I slibe et egetræsgulv på 60 m²?" } })).ok()).toBeTruthy();
  const c = await page.request.post(`${pub}/conversations/${conv.conversation_id}/contact`, { headers: { ...h, "x-visitor-token": conv.visitor_token }, data: { name: who, phone: "20 30 40 50", window: "asap", consent: true } });
  expect(c.ok(), await c.text()).toBeTruthy();
  return conv.conversation_id as string;
}

test("I01–I05 · Opkald: listen, søgning, filter, detalje, henvendelse og opgave – ét forløb", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const who = `Henrik Villumsen ${Date.now() % 100000}`;
  const convId = await seedChatLead(page, wsId, who);

  // I01: the old route still lands on the unified list; the row shows channel, name and «Til dig»
  await page.goto("/app/inbox");
  await expect(page).toHaveURL(/\/app\/opkald/);
  const row = page.getByRole("link", { name: new RegExp(who) });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Webchat");
  // filters and search
  await page.goto("/app/opkald?f=to_you");
  await expect(page.getByRole("link", { name: new RegExp(who) })).toBeVisible();
  await page.goto("/app/opkald?f=booked");
  await expect(page.getByRole("link", { name: new RegExp(who) })).toHaveCount(0);
  await page.goto("/app/opkald");
  await page.getByPlaceholder(/Søg/i).fill("egetræsgulv");
  await page.getByPlaceholder(/Søg/i).press("Enter");
  await expect(page.getByRole("link", { name: new RegExp(who) })).toBeVisible();
  await page.screenshot({ path: `${EVID}/I01/${info.project.name}-opkald-soeg.png`, fullPage: true });

  // I02: detail with the transcript and the linked enquiry
  await page.goto(`/app/opkald/${convId}`);
  await expect(page.getByRole("list", { name: /udskrift/i }).getByText("Kan I slibe et egetræsgulv på 60 m²?", { exact: true })).toBeVisible();
  const open = page.getByRole("link", { name: /henvendelse/i }).first();
  await expect(open).toBeVisible();
  await page.screenshot({ path: `${EVID}/I02/${info.project.name}-detalje.png`, fullPage: true });

  // I04/I05: the enquiry page has the follow-up task; completing it sticks after reload
  await open.click();
  await expect(page).toHaveURL(/\/app\/opkald\/henvendelser\/[0-9a-f-]{36}/);
  const task = page.getByRole("checkbox").first();
  await expect(task).toBeVisible();
  await task.check();
  await page.reload();
  await expect(page.getByRole("checkbox").first()).toBeChecked();
  await page.screenshot({ path: `${EVID}/I04/${info.project.name}-henvendelse.png`, fullPage: true });
});

test("I03 · «I dag»-flisen «Henvendelser» og ukendte id'er giver ikke en serverfejl", async ({ page }, info) => {
  // F-V2-04-I03 (fixed): /app/opkald/henvendelser and /app/opkald/opgaver have their own page («Til dig»), so they no
  // longer fall through to /app/opkald/[id]; an id the backend rejects (404/422) is a 404 page, not a 500.
  await freshOwner(page, info);
  // the tile on I dag links here (web/src/app/app/(admin)/page.tsx: href="/app/opkald/henvendelser")
  await page.goto("/app");
  await page.locator('a[href="/app/opkald/henvendelser"]').first().click();
  await expect(page).toHaveURL(/\/app\/opkald\?f=to_you$/);
  await expect(page.getByText("Siden kunne ikke vises")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.screenshot({ path: `${EVID}/I03/${info.project.name}-henvendelser-liste.png`, fullPage: true });
  for (const p of ["/app/opkald/henvendelser", "/app/opkald/opgaver"]) {
    const list = await page.goto(p);
    expect(list!.status(), `${p} (I dag tile / assistant chip) leads to a server error`).toBeLessThan(400);
    await expect(page).toHaveURL(/\/app\/opkald\?f=to_you$/);
  }
  const unknown = await page.goto("/app/opkald/00000000-0000-4000-8000-000000000000");
  expect(unknown!.status(), "an unknown/foreign conversation id must be 404, not 500").toBe(404);
  const unknownLead = await page.goto("/app/opkald/henvendelser/00000000-0000-4000-8000-000000000000");
  expect(unknownLead!.status(), "an unknown/foreign enquiry id must be 404, not 500").toBe(404);
  const notUuid = await page.goto("/app/opkald/henvendelser/ikke-et-id");
  expect(notUuid!.status(), "a malformed enquiry id must be 404, not 500").toBe(404);
});

test("R04–R07 · gamle receptionsadresser fra kravene ender ikke på en 404", async ({ page }, info) => {
  // F-V2-07-R05 (fixed): next.config.ts MOVED redirects the four requirement routes to their v2 sheets.
  await freshOwner(page, info);
  const dead: string[] = [];
  for (const p of ["/app/reception/widget", "/app/reception/assistant", "/app/reception/test", "/app/reception/routing"]) {
    const r = await page.goto(p);
    if (!r || r.status() >= 400) dead.push(`${p} → ${r?.status()}`);
  }
  expect(dead, "requirement routes without a v2 redirect").toEqual([]);
});

test("X21 · salgskanalen: en kunde (ikke operatør) ser kun «kun for operatører»", async ({ page }) => {
  await login(page, SEEDED.owner, process.env.SEED_DEMO_PASSWORD ?? "E2e-Demo-Password-2026");
  for (const p of ["/app/operator/salg", "/app/operator/salg/find", "/app/operator/salg/opkald"]) {
    await page.goto(p);
    await expect(page.getByText(/kun for Dialogbot-operatører/i)).toBeVisible();
  }
  expect((await page.request.get("/api/backend/operator/salg")).status()).toBe(403);
  expect((await page.request.post("/api/backend/operator/salg/test-calls", { headers: CSRF, data: { company_id: "00000000-0000-0000-0000-000000000000", script_id: "00000000-0000-0000-0000-000000000000", phone: "+4520304050", accepted_test: true } })).status()).toBe(403);
  await page.screenshot({ path: `${EVID}/X21/kunde-ser-salg.png`, fullPage: true });
});
