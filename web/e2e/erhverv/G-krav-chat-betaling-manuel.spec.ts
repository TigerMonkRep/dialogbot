import { expect, test, type Page, type TestInfo } from "@playwright/test";
import type { Server } from "node:http";
import { DEMO_PASSWORD, PREVIEW_CODE, latestMailLink, serve, shot, uniqueEmail } from "../helpers";

/* Fürster 11/11 23:29 – three binding requirements for the guide (/opsaetning/1–3):
 *  K1 webchat without a phone number: a chat-only business goes through the guide, turns the chat on and it answers on a
 *     test page – no number, routing or telephony anywhere.
 *  K2 the guide ends on payment: set up but not paid → subscription/checkout with one plain next step; paid → «I dag».
 *  K3 manual setup around the guide: a visible «Sæt op selv» on every viewport, the ordinary settings pages work without
 *     the guide, what is done there counts in the guide's progress (and the other way round), and a way back.
 * A real new Erhverv customer each time: /signup → verify-mail link → /opsaetning/1. Fake adapters only. */
const CSRF = { "x-requested-with": "dialogbot" };
const PORT = Number(process.env.E2E_SITE_PORT ?? 4000);
const SITE = `http://127.0.0.1:${PORT}`;
const servers: Server[] = [];
test.afterEach(async () => { for (const s of servers.splice(0)) await new Promise((r) => s.close(r)); });

async function signup(page: Page, info: TestInfo, company: string) {
  await page.goto("/preview");
  const code = page.getByLabel("Invitationskode");
  if (await code.isVisible().catch(() => false)) {
    await code.fill(PREVIEW_CODE);
    await page.getByRole("button", { name: "Lås op og se forsiden" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/preview"));
  }
  await page.goto("/signup?intent=reception");
  await page.getByLabel("Dit navn").fill("Rebotti Ejer");
  await page.getByLabel("E-mail").fill(uniqueEmail("krav", info));
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/verify-email/);
  await page.goto(await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/));
  await page.getByRole("link", { name: /Fortsæt til arbejdsrum/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/1/);
  await page.getByLabel("Navn (som den siger det)").fill(company);
  await page.getByRole("button", { name: "Videre" }).click();
  await expect(page.getByLabel("Hvad I laver – én sætning")).toBeVisible({ timeout: 15_000 });
  const ws = (await (await page.request.get("/api/backend/workspaces")).json()) as { id: string; name: string }[];
  return ws.find((w) => w.name === company)!.id;
}

const get = async (page: Page, path: string) => (await page.request.get(`/api/backend${path}`)).json();
const stepper = (page: Page, n: number) => page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: new RegExp(`^Trin ${n}`) });

test("K1 · kun webchat: guiden kræver intet telefonnummer, chatten tændes og svarer på en testside", async ({ page, browser }, info) => {
  const wsId = await signup(page, info, `Rebotti chat ${info.project.name} ${Date.now()}`);
  // trin 1: chat instead of the phone; no phone number typed anywhere
  const phoneCard = page.getByRole("checkbox", { name: /Tage telefonen/ });
  if (await phoneCard.isChecked()) await phoneCard.uncheck();
  await page.getByRole("checkbox", { name: /Svare på hjemmesiden/ }).check();
  await page.getByLabel("Hjemmesidens adresse").fill(`${SITE}/`);
  await page.getByLabel("Hvad I laver – én sætning").fill("Italiensk restaurant og take-away i Aarhus");
  await page.getByLabel("Åbningstider").fill("Man–fre 11–22");
  await expect(page.getByText("Udfyld navn og hvad I laver for at gå videre.")).toHaveCount(0);
  const next = page.getByRole("button", { name: /Videre til trin 3/ });
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page).toHaveURL(/\/opsaetning\/3$/, { timeout: 20_000 });
  await expect(stepper(page, 1)).toHaveAccessibleName(/fuldført/);
  expect((await get(page, `/workspaces/${wsId}/profile`)).phone).toBeNull();

  // trin 3: no phone part; the chat is turned on here
  await expect(page.getByRole("heading", { name: "Telefon", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Tænd webchatten" }).click();
  await expect(page.locator("pre").filter({ hasText: "<script" })).toBeVisible({ timeout: 15_000 });
  await expect(stepper(page, 3)).toHaveAccessibleName(/fuldført/);
  await shot(page, info, "k1-trin3-chat-taendt");
  const tel = await get(page, `/workspaces/${wsId}/telephony`);
  expect(tel.status.code, "ingen telefoni sat op eller købt").toBe("not_started");

  // the chat works on a test page – without any number
  const w = await get(page, `/workspaces/${wsId}/webchat`);
  expect(w.enabled).toBe(true);
  servers.push(await serve(PORT, `<!doctype html><html lang="da"><head><title>Rebotti</title></head><body><h1>Rebotti</h1>${w.embed_code}</body></html>`));
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const site = await ctx.newPage();
  await site.goto(`${SITE}/`);
  await site.getByRole("button", { name: "Åbn chat" }).click();
  const chat = site.frameLocator('iframe[title^="Chat med"]');
  await chat.getByLabel("Din besked").fill("Har I åbent på fredag?");
  await chat.locator("form:not(.contact)").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("[fake] svar på: Har I åbent på fredag?")).toBeVisible({ timeout: 15_000 });
  await shot(site, info, "k1-testside-chat");
  await ctx.close();

  // done in the guide = shows in the ordinary settings (and «I dag» speaks about the chat, not a phone)
  await page.goto("/app/indstillinger?ark=webchat");
  await expect(page.getByRole("switch", { name: "Vis widgetten på hjemmesiden" })).toBeChecked();
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Webchatten er tændt" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sæt telefonen op" })).toHaveCount(0);
});

test("K2 · guiden ender på betaling: ikke betalt → abonnement med ét næste skridt; betalt → «I dag»", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti betal ${info.project.name} ${Date.now()}`);
  // Everything set up (chat only) – quickly through the API, the guide is K1's subject.
  const prof = await get(page, `/workspaces/${wsId}/profile`);
  await page.request.put(`/api/backend/workspaces/${wsId}/profile`, { headers: CSRF, data: { ...prof, expected_version: prof.version, description: "Italiensk restaurant i Aarhus", website_url: `${SITE}/`, manual_setup: false } });
  const goals = await get(page, `/workspaces/${wsId}/goals`);
  await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...goals, expected_version: goals.version, product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false } });
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "fact", title: "Åbent", content: { text: "Vi har åbent alle dage 11–22." } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF, data: {} });
  const w = await get(page, `/workspaces/${wsId}/webchat`);
  expect((await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: w.version, enabled: true, allowed_origins: [SITE], greeting: "" } })).ok()).toBeTruthy();

  // not paid: trin 3's one action is the subscription, and «I dag» says it too
  await page.goto("/opsaetning/3");
  await expect(page.getByText("Sidste skridt: bekræft abonnementet.")).toBeVisible();
  await page.getByRole("link", { name: "Videre til abonnement og betaling" }).click();
  await expect(page).toHaveURL(/\/app\/konto\?fra=opsaetning/);
  await expect(page.getByText(/^Sidste skridt: bekræft abonnementet herunder/)).toBeVisible();
  await shot(page, info, "k2-betaling");
  await page.context().addCookies([{ name: "db_setup_later", value: "1", url: page.url() }]);
  await page.goto("/app");
  await expect(page.getByRole("link", { name: /vælg abonnement og betaling/ })).toBeVisible();

  // pay: confirm the subscription (and the card, when card payment is set up in this environment)
  await page.goto("/app/konto?fra=opsaetning#abonnement");
  await page.getByRole("button", { name: "Bekræft abonnement" }).click();
  await expect(page.getByText(/Bekræftet · aftale v1/)).toBeVisible();
  const acc = await get(page, `/workspaces/${wsId}/billing/account`);
  if (acc.configured) {
    // Stripe set up: the card is the last step (Stripe Checkout itself is not driven here)
    await expect(page.getByText("Abonnementet er bekræftet. Sidste skridt: tilføj et betalingskort herunder.")).toBeVisible();
    test.info().annotations.push({ type: "stripe", description: "kort-trinnet vist; Stripe Checkout ikke kørt" });
    return;
  }
  await expect(page.getByText("Du er live. Abonnementet er på plads.")).toBeVisible();
  await page.getByRole("link", { name: "Gå til I dag" }).first().click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("link", { name: /vælg abonnement og betaling/ })).toHaveCount(0);
  await page.goto("/opsaetning/3");
  await expect(page.getByRole("link", { name: "Gå til I dag" })).toBeVisible();
  await shot(page, info, "k2-betalt");
});

test("K3 · «Sæt op selv»: synlig vej ud, manuel opsætning tæller i guiden, og vejen tilbage", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti manuel ${info.project.name} ${Date.now()}`);
  // the way out is visible on every viewport (it used to be hidden on mobile)
  const out = page.getByRole("link", { name: "Sæt op selv" });
  await expect(out).toBeVisible();
  await out.click();
  await expect(page).toHaveURL(/\/app\/indstillinger$/);
  await expect(page.getByText(/Guiden er ikke færdig · næste: trin 1/)).toBeVisible();
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app$/); // not forced back into the guide
  await expect(page.getByText(/Opsætningen er ikke færdig · næste: trin 1/)).toBeVisible();

  // by hand: the business, the knowledge and the chat (the chat in the ordinary webchat settings)
  const prof = await get(page, `/workspaces/${wsId}/profile`);
  await page.request.put(`/api/backend/workspaces/${wsId}/profile`, { headers: CSRF, data: { ...prof, expected_version: prof.version, description: "Italiensk restaurant i Aarhus", website_url: `${SITE}/`, manual_setup: false } });
  const goals = await get(page, `/workspaces/${wsId}/goals`);
  await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...goals, expected_version: goals.version, product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false } });
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "fact", title: "Åbent", content: { text: "Vi har åbent alle dage 11–22." } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF, data: {} });
  await page.goto("/app/indstillinger?ark=webchat");
  await page.getByRole("switch", { name: "Vis widgetten på hjemmesiden" }).check();
  await page.getByLabel("Godkendte domæner").fill(SITE);
  await page.getByRole("button", { name: "Gem indstillinger" }).click();
  await expect.poll(async () => (await get(page, `/workspaces/${wsId}/webchat`)).enabled, { timeout: 15_000 }).toBe(true);

  // the guide counts it: trin 1 and trin 3 done, nothing left but the subscription
  await page.goto("/opsaetning/3");
  await expect(stepper(page, 1)).toHaveAccessibleName(/fuldført/);
  await expect(stepper(page, 3)).toHaveAccessibleName(/fuldført/);
  await expect(page.getByRole("heading", { name: "Dialogbot er tændt" })).toBeVisible();
  await shot(page, info, "k3-manuelt-talt-med");
  await page.goto("/app/indstillinger");
  await expect(page.getByText(/Guiden er ikke færdig/)).toHaveCount(0);
  await page.goto("/app");
  await expect(page.getByText(/Opsætningen er ikke færdig/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /vælg abonnement og betaling/ })).toBeVisible();
});
