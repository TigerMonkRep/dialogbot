import { expect, test, type Page, type TestInfo } from "@playwright/test";
import type { Server } from "node:http";
import { DEMO_PASSWORD, PREVIEW_CODE, latestMailLink, serve, shot, uniqueEmail } from "../helpers";

/* Fürster 11/11 23:29 – three binding requirements for the guide, as changed by Fürster 12/11 09:25 (the chat does NOT go
 * live without a paid subscription; the steps follow the chosen channels: Virksomhed → Viden → Chat/Telefon → Betaling):
 *  K1 webchat without a phone number: a chat-only business goes through the guide with no number, routing or telephony
 *     anywhere; the chat answers no visitor before the subscription is paid – and does after it is switched on.
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
  await expect(page).toHaveURL(/\/opsaetning\/virksomhed/);
  await page.getByLabel("Navn (som den siger det)").fill(company);
  await page.getByRole("button", { name: "Videre" }).click();
  await expect(page.getByLabel("Hvad I laver – én sætning")).toBeVisible({ timeout: 15_000 });
  const ws = (await (await page.request.get("/api/backend/workspaces")).json()) as { id: string; name: string }[];
  return ws.find((w) => w.name === company)!.id;
}

const get = async (page: Page, path: string) => (await page.request.get(`/api/backend${path}`)).json();
const stepper = (page: Page, n: number) => page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: new RegExp(`^Trin ${n}`) });

test("K1 · kun webchat: intet telefonnummer i guiden; chatten svarer ingen besøgende før betaling – og gør det efter", async ({ page, browser }, info) => {
  const wsId = await signup(page, info, `Rebotti chat ${info.project.name} ${Date.now()}`);
  // Virksomhed: chat instead of the phone; no phone number typed anywhere
  const phoneCard = page.getByRole("checkbox", { name: /Tage telefonen/ });
  if (await phoneCard.isChecked()) await phoneCard.uncheck();
  await page.getByRole("checkbox", { name: /Svare på hjemmesiden/ }).check();
  await page.getByLabel("Hjemmesidens adresse").fill(`${SITE}/`);
  await page.getByLabel("Hvad I laver – én sætning").fill("Italiensk restaurant og take-away i Aarhus");
  await page.getByLabel("Åbningstider").fill("Man–fre 11–22");
  await expect(page.getByText("Udfyld navn og hvad I laver for at gå videre.")).toHaveCount(0);
  const next = page.getByRole("button", { name: "Videre til trin 2: Viden" });
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page).toHaveURL(/\/opsaetning\/viden$/, { timeout: 20_000 });
  await expect(stepper(page, 1)).toHaveAccessibleName(/fuldført/);
  expect((await get(page, `/workspaces/${wsId}/profile`)).phone).toBeNull();
  await expect(page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: /Telefon/ })).toHaveCount(0);

  // Chat: no phone part; set up and tried, but not live
  await page.getByRole("link", { name: "Videre til trin 3: Chat" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/chat$/);
  await expect(page.getByRole("heading", { name: "Telefon", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.locator("pre").filter({ hasText: "<script" })).toBeVisible();
  await expect(stepper(page, 3)).toHaveAccessibleName(/fuldført/);
  await expect(page.getByText("Chatten går live, når abonnementet er på plads")).toBeVisible();
  await shot(page, info, "k1-chat-ikke-live");
  const tel = await get(page, `/workspaces/${wsId}/telephony`);
  expect(tel.status.code, "ingen telefoni sat op eller købt").toBe("not_started");
  let w = await get(page, `/workspaces/${wsId}/webchat`);
  expect(w.enabled).toBe(false);

  // the test page with the line: before payment no visitor gets a chat (the backend says so, not only the UI)
  servers.push(await serve(PORT, `<!doctype html><html lang="da"><head><title>Rebotti</title></head><body><h1>Rebotti</h1>${w.embed_code}</body></html>`));
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  let site = await ctx.newPage();
  const st = site.waitForResponse((r) => r.url().endsWith("/status"));
  await site.goto(`${SITE}/`);
  expect((await (await st).json()).available).toBe(false);
  await site.waitForTimeout(500);
  await expect(site.getByRole("button", { name: "Åbn chat" })).toHaveCount(0);
  const refused = await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: w.version, enabled: true, allowed_origins: w.allowed_origins, greeting: "" } });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).code).toBe("subscription_required");

  // paid (confirmed; no Stripe here) → «Tænd webchatten» in the chat step → it answers on the test page, without any number
  await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } });
  await page.reload();
  await page.getByRole("button", { name: "Tænd webchatten" }).click();
  await expect(page.getByText("Chatten er live og svarer besøgende på hjemmesiden.")).toBeVisible({ timeout: 15_000 });
  w = await get(page, `/workspaces/${wsId}/webchat`);
  expect(w.enabled && w.available).toBe(true);
  site = await ctx.newPage();
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

test("K2 · guiden ender på et synligt Betaling-trin: ikke betalt → ét næste skridt; betalt → gå live → «I dag»", async ({ page }, info) => {
  const wsId = await signup(page, info, `Rebotti betal ${info.project.name} ${Date.now()}`);
  // Everything set up (chat only) – quickly through the API, the guide is K1's subject.
  const prof = await get(page, `/workspaces/${wsId}/profile`);
  await page.request.put(`/api/backend/workspaces/${wsId}/profile`, { headers: CSRF, data: { ...prof, expected_version: prof.version, description: "Italiensk restaurant i Aarhus", website_url: `${SITE}/`, manual_setup: false } });
  const goals = await get(page, `/workspaces/${wsId}/goals`);
  await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...goals, expected_version: goals.version, product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false } });
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "fact", title: "Åbent", content: { text: "Vi har åbent alle dage 11–22." } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF, data: {} });
  const w = await get(page, `/workspaces/${wsId}/webchat`);
  expect((await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: w.version, enabled: false, allowed_origins: [SITE], greeting: "" } })).ok()).toBeTruthy();

  // not paid: the old address of the last step leads to Betaling, a visible step with one next action
  await page.goto("/opsaetning/3");
  await expect(page).toHaveURL(/\/opsaetning\/betaling$/);
  await expect(stepper(page, 4)).toHaveAttribute("aria-current", "step");
  await expect(page.getByTestId("betaling-status")).toHaveText(/^Næste skridt: bekræft abonnementet/);
  await expect(page.getByRole("button", { name: "Gå live" })).toBeDisabled();
  await shot(page, info, "k2-betaling");
  await page.context().addCookies([{ name: "db_setup_later", value: "1", url: page.url() }]);
  await page.goto("/app");
  await expect(page.getByRole("link", { name: /vælg abonnement og betaling/ })).toBeVisible();
  // Konto still works as the way to pay
  await page.goto("/app/konto?fra=opsaetning#abonnement");
  await expect(page.getByText(/^Sidste skridt: bekræft abonnementet herunder/)).toBeVisible();

  // pay in the guide: confirm the subscription (and the card, when card payment is set up in this environment)
  await page.goto("/opsaetning/betaling");
  await page.getByRole("button", { name: "Bekræft abonnement" }).click();
  await expect(page.getByText(/Bekræftet · aftale v1/)).toBeVisible();
  const acc = await get(page, `/workspaces/${wsId}/billing/account`);
  if (acc.configured) {
    await expect(page.getByTestId("betaling-status")).toHaveText("Abonnementet er bekræftet. Sidste skridt: tilføj et betalingskort.");
    test.info().annotations.push({ type: "stripe", description: "kort-trinnet vist; Stripe Checkout ikke kørt" });
    return;
  }
  await expect(page.getByTestId("betaling-status")).toHaveText("Abonnementet er på plads. Nu kan Dialogbot gå live.");
  await page.getByRole("button", { name: "Gå live" }).click();
  await expect(page).toHaveURL(/\/app\?taendt=1$/, { timeout: 20_000 });
  await expect(page.getByRole("link", { name: /vælg abonnement og betaling/ })).toHaveCount(0);
  await expect(page.getByTestId("setup-checklist")).toHaveCount(0);
  await page.goto("/opsaetning/betaling");
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
  await expect(page.getByText(/Guiden er ikke færdig · næste: Virksomhed/)).toBeVisible();
  await expect(page.getByTestId("setup-checklist").getByText("Tilbage til guiden")).toBeVisible();
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app$/); // not forced back into the guide
  await expect(page.getByText(/Opsætningen er ikke færdig · næste: Virksomhed/)).toBeVisible();

  // by hand: the business, the knowledge and the chat (the chat in the ordinary webchat settings)
  const prof = await get(page, `/workspaces/${wsId}/profile`);
  await page.request.put(`/api/backend/workspaces/${wsId}/profile`, { headers: CSRF, data: { ...prof, expected_version: prof.version, description: "Italiensk restaurant i Aarhus", website_url: `${SITE}/`, manual_setup: false } });
  const goals = await get(page, `/workspaces/${wsId}/goals`);
  await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...goals, expected_version: goals.version, product_intent: "reception", inbound_phone: false, webchat: true, callback: true, booking: false } });
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "fact", title: "Åbent", content: { text: "Vi har åbent alle dage 11–22." } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF, data: {} });
  await page.goto("/app/indstillinger?ark=webchat");
  await page.getByLabel("Godkendte domæner").fill(SITE);
  await page.getByRole("button", { name: "Gem indstillinger" }).click();
  await expect.poll(async () => (await get(page, `/workspaces/${wsId}/webchat`)).allowed_origins, { timeout: 15_000 }).toEqual([SITE]);
  // switching it on by hand before paying is refused, and says why
  await page.getByRole("switch", { name: "Vis widgetten på hjemmesiden" }).check();
  await page.getByRole("button", { name: "Gem indstillinger" }).click();
  await expect(page.getByText("Chatten går live, når abonnementet er på plads").first()).toBeVisible();
  expect((await get(page, `/workspaces/${wsId}/webchat`)).enabled).toBe(false);

  // the guide counts it: Virksomhed, Viden and Chat done, nothing left but the subscription
  await page.goto("/opsaetning/betaling");
  for (const n of [1, 2, 3]) await expect(stepper(page, n)).toHaveAccessibleName(/fuldført/);
  await shot(page, info, "k3-manuelt-talt-med");
  await page.goto("/app/indstillinger");
  await expect(page.getByText(/Guiden er ikke færdig/)).toHaveCount(0);
  await page.goto("/app");
  await expect(page.getByText(/Opsætningen er ikke færdig/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /vælg abonnement og betaling/ })).toBeVisible();

  // paying by hand (Konto) and switching on by hand (settings) count too: the guide is done
  await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } });
  await page.goto("/app/indstillinger?ark=webchat");
  await page.getByRole("switch", { name: "Vis widgetten på hjemmesiden" }).check();
  await page.getByRole("button", { name: "Gem indstillinger" }).click();
  await expect.poll(async () => (await get(page, `/workspaces/${wsId}/webchat`)).enabled, { timeout: 15_000 }).toBe(true);
  await page.goto("/opsaetning/betaling");
  await expect(stepper(page, 4)).toHaveAccessibleName(/fuldført/);
  await expect(page.getByRole("heading", { name: "Dialogbot er tændt" })).toBeVisible();
  await page.goto("/app");
  await expect(page.getByTestId("setup-checklist")).toHaveCount(0);
});
