import { expect, test, type Page } from "@playwright/test";
import { freshOwner, latestMailLink } from "../../helpers";
import { api, colleague, completeProfile, freshUser, snap } from "./e2b";

/* QA X19 (E2B) – in-app chatten «Ændr noget»: guider med almindelige ord (svar + link), ændrer indstillinger (før → efter → Godkend),
 * og det den ikke kan, lander som kundeønske hos admin (/app/operator/oensker + mail til operatører).
 * Kilde: web/src/components/assistant.tsx; app/modules/assistant/{router,service,requests,operator_router}.py; fake: app/modules/ai/provider.py _change. */
const ID = "X19";

async function chat(page: Page) {
  await page.goto("/app");
  if ((page.viewportSize()?.width ?? 1440) < 1280) await page.getByRole("button", { name: "Ændr noget" }).click();
  const ask = page.getByLabel("Skriv, hvad du vil ændre").filter({ visible: true });
  const log = page.getByRole("log").filter({ visible: true });
  const say = async (t: string) => { await ask.fill(t); await ask.press("Enter"); await expect(page.getByText("Tænker …").filter({ visible: true })).toHaveCount(0, { timeout: 15_000 }); };
  return { ask, log, say };
}

test("X19 · guider: svar med link til rette side; ugyldigt link fra modellen vises ikke", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const { log, say } = await chat(page);
  await say("Hvordan viderestiller jeg min telefon?");
  const link = log.getByRole("link").last();
  await expect(link).toHaveAttribute("href", /\/app\/indstillinger\?ark=telefoni/);
  await say("hvad er en ugyldig side?");
  await snap(page, ID, info, "svar-links");
  await expect(log.locator('a[href="/ikke/en/side"]')).toHaveCount(0);
});

test("X19 · ændrer: pris med egne ord → kort → Godkend → viden opdateret; Godkend igen via API afvises; andres forslag 404", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const { log, say } = await chat(page);
  let proposalId = "";
  page.on("response", async (r) => { if (r.url().endsWith("/assistant/changes") && r.request().method() === "POST") { const b = await r.json().catch(() => null); if (b?.proposal) proposalId = b.proposal.id; } });
  await say("Gulvafslibning koster 145 kr pr. m2");
  const card = log.getByRole("group", { name: /Ændring:/ }).last();
  await expect(card).toBeVisible();
  const liveBefore = JSON.stringify((await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body.items);
  expect(liveBefore).not.toContain("14500");
  await card.getByRole("button", { name: "Godkend" }).dblclick();
  await expect(card.getByText(/Godkendt og gemt/)).toBeVisible();
  await expect(card.getByRole("alert")).toHaveCount(0);
  expect(JSON.stringify((await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body.items)).toContain("14500");
  expect((await api(page).send("POST", `/workspaces/${wsId}/assistant/changes/${proposalId}/apply`)).status).toBe(409);
  // a colleague (admin) cannot apply someone else's proposal
  const admin = await colleague(page, browser, info, wsId, "admin");
  expect((await api(admin.page).send("POST", `/workspaces/${wsId}/assistant/changes/${proposalId}/apply`)).status).toBe(404);
  await admin.ctx.close();
  await snap(page, ID, info, "pris-godkendt");
});

test("X19 · roller: læser får intet ændringskort; medarbejder kan ikke ændre det, der kræver administrator", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const reader = await colleague(page, browser, info, wsId, "reader");
  const r = await chat(reader.page);
  await r.say("åbningstider man-fre 7-15");
  await expect(r.log.getByText(/kan kun ændres af/)).toBeVisible();
  await expect(r.log.getByRole("button", { name: "Godkend" })).toHaveCount(0);
  await reader.ctx.close();
  const staff = await colleague(page, browser, info, wsId, "staff");
  const s = await chat(staff.page);
  await s.say("Velkomsten i webchatten skal være: Hej med dig");
  await snap(staff.page, ID, info, "medarbejder-webchat");
  await expect(s.log.getByRole("button", { name: "Godkend" }), "medarbejder får et kort, som serveren vil afvise").toHaveCount(0);
  await staff.ctx.close();
});

test("X19 · kundeønske: sendes til admin, gentagelse tælles, operatør ser det med kundens ord og får mail; kunde kan ikke se listen", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const op = await freshUser(browser, info, "e2b-op");
  expect((await api(op.page).send("POST", "/dev/operator/self")).status).toBe(200);
  const tag = `Ordrestyring${Date.now()}`;
  const { log, say } = await chat(page);
  await say(`Kan I lave en integration til ${tag}?`);
  await expect(log.getByText("Sendt til Dialogbot-teamet")).toBeVisible();
  await say(`Ønske: integration til ${tag} tak`);
  await expect(log.getByText(/har fået det ønske før/)).toBeVisible();
  await snap(page, ID, info, "oenske-kunde");
  expect((await api(page).get("/operator/assistant/requests")).status).toBe(403);
  const list = (await api(op.page).get(`/operator/assistant/requests?workspace_id=${wsId}`)).body;
  const mine = list.items.filter((i: { text: string }) => i.text.includes(tag));
  expect(mine).toHaveLength(1);
  expect(mine[0]).toMatchObject({ category: "integrations", status: "new", times_asked: 2 });
  await expect.poll(async () => { try { return await latestMailLink(op.page.request, new RegExp(`Nyt ønske[^\\n]*|${tag}`)); } catch { return ""; } }, { timeout: 40_000 }).toBeTruthy();
  const ows = (await api(op.page).send("POST", "/workspaces", { name: `QA Operatør ${Date.now()}`, product_intent: "reception" })).body;
  await op.page.request.post("/api/auth/workspace", { headers: { "x-requested-with": "dialogbot" }, data: { workspace_id: ows.id } });
  await op.ctx.addCookies([{ name: "db_setup_later", value: "1", url: process.env.BASE_URL ?? "http://localhost:3000" }]);
  await op.page.goto("/app/operator/oensker");
  await expect(op.page.getByText(tag).first()).toBeVisible();
  await snap(op.page, ID, info, "oenske-operator");
  const patched = await api(op.page).send("PATCH", `/operator/assistant/requests/${mine[0].id}`, { status: "planned", admin_note: "intern QA-note" });
  expect(patched.status).toBe(200);
  // the internal note must not leak into the customer's activity log
  const act = await api(page).get(`/workspaces/${wsId}/audit?limit=50`);
  if (act.status === 200) expect(JSON.stringify(act.body)).not.toContain("intern QA-note");
  await op.ctx.close();
});

test("X19 · fejl: 500 fra chatten og ved Godkend giver en besked – intet hænger", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const { log, say } = await chat(page);
  await page.route(`**/api/backend/workspaces/${wsId}/assistant/changes`, (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Intern fejl (QA)" }) }));
  await say("åbningstider man-fre 7-15");
  await expect(log.getByText(/Intern fejl \(QA\)|Det lykkedes ikke/)).toBeVisible();
  await page.unroute(`**/api/backend/workspaces/${wsId}/assistant/changes`);
  await say("åbningstider man-fre 7-15");
  await page.route(/\/assistant\/changes\/[^/]+\/apply$/, (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Intern fejl (QA)" }) }));
  const card = log.getByRole("group", { name: /Ændring:/ }).last();
  await card.getByRole("button", { name: "Godkend" }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  await expect(card.getByRole("button", { name: "Godkend" })).toBeEnabled();
  expect(JSON.stringify((await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body.items)).not.toContain("07:00");
  await snap(page, ID, info, "fejl");
});
