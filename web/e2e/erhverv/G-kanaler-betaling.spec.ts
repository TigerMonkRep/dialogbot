import { expect, test, type Page, type TestInfo } from "@playwright/test";
import type { Server } from "node:http";
import { DEMO_PASSWORD, PREVIEW_CODE, latestMailLink, serve, shot, uniqueEmail } from "../helpers";

/* Fürster 12/11 09:25 (binding): the guide's steps follow the channels the customer chooses – Virksomhed → Viden →
 * Kanaler (Telefon and/or Chat) → Betaling – and NEITHER the chat NOR the phone goes live without a paid subscription.
 * Before payment the owner may try the chat in a preview, but a visitor on the customer's website gets no chat.
 * A real new Erhverv customer each time: /signup → verify-mail link → the guide. Fake adapters only; no Stripe here, so
 * «betalt» = the confirmed subscription (#18's rule). Desktop 1440 and mobile 390. */
const CSRF = { "x-requested-with": "dialogbot" };
const PORT = Number(process.env.E2E_SITE_PORT ?? 4000);
const SITE = `http://127.0.0.1:${PORT}`;
const API = process.env.API_BASE_URL ?? "http://localhost:8000";
const VAPI = { authorization: `Bearer ${process.env.VAPI_SERVER_SECRET ?? "e2e-only-vapi-secret-0123456789"}` };
const servers: Server[] = [];
const close = (s: Server) => new Promise((r) => s.close(r));
test.afterEach(async () => { for (const s of servers.splice(0)) await close(s); });

const TEXT = `Spørgsmål: Har I åbent om lørdagen?
Svar: Ja, lørdag 10–14.
Spørgsmål: Kan man bestille bord?
Svar: Ja, ring eller skriv i chatten.
Vi dækker: Aarhus C og Aarhus N`;

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
  await page.getByLabel("E-mail").fill(uniqueEmail("kanal", info));
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
const post = async (page: Page, path: string, data: unknown = {}) => {
  const r = await page.request.post(`/api/backend${path}`, { headers: CSRF, data });
  expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
  return r.json();
};
const nav = (page: Page) => page.getByRole("navigation", { name: "Opsætning" });
const noOverflow = async (page: Page) => expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "ingen vandret scroll").toBeTruthy();
const sitePage = (body: string) => `<!doctype html><html lang="da"><head><title>Rebotti</title></head><body><h1>Rebotti</h1>${body}</body></html>`;

/** The channel cards in Virksomhed (B): exactly the wanted ones ticked. */
async function channels(page: Page, want: { phone: boolean; chat: boolean }) {
  for (const [name, on] of [[/Tage telefonen/, want.phone], [/Svare på hjemmesiden/, want.chat]] as const) {
    const box = page.getByRole("checkbox", { name });
    if ((await box.isChecked()) !== on) await box.setChecked(on);
  }
}

/** The visitor on the customer's website: is there a chat at all? (the loader asks /status first) */
async function visitorSeesChat(page: Page, browserCtx: { newPage: () => Promise<Page> }) {
  const site = await browserCtx.newPage();
  const status = site.waitForResponse((r) => r.url().includes("/public/webchat/") && r.url().endsWith("/status"));
  await site.goto(`${SITE}/`);
  const ok = (await (await status).json()).available as boolean;
  if (!ok) await site.waitForTimeout(500);
  const shown = (await site.getByRole("button", { name: "Åbn chat" }).count()) > 0;
  return { site, ok, shown };
}

/** The simulated provider rings the Dialogbot number: the owner's test call passes. */
async function passTestCall(page: Page, wsId: string, info: TestInfo) {
  const dest = (await get(page, `/workspaces/${wsId}/telephony`)).destination.e164 as string;
  const callId = `call_kanal_${info.project.name}_${Date.now()}`;
  const req = await page.request.post(`${API}/api/v1/webhooks/vapi`, { headers: VAPI, data: { message: { type: "assistant-request", call: { id: callId, customer: { number: "+4540404040" } }, phoneNumber: { number: dest } } } });
  expect((await req.json()).assistant.firstMessage).toContain("Dette er et prøveopkald");
  const report = await page.request.post(`${API}/api/v1/webhooks/vapi`, { headers: VAPI, data: { message: {
    type: "end-of-call-report", endedReason: "customer-ended-call", analysis: { summary: "Prøveopkald." }, phoneNumber: { number: dest },
    call: { id: callId, customer: { number: "+4520304050" }, startedAt: new Date(Date.now() - 65_000).toISOString(), endedAt: new Date().toISOString() },
    artifact: { messages: [{ role: "bot", message: "Dette er et prøveopkald." }, { role: "user", message: "Hej." }] } } } });
  expect((await report.json()).outcome).toBe("applied");
}

/** Number → code → (documents) in the Telefon step's UI. */
async function phoneNumberInGuide(page: Page, wsId: string, own: string) {
  await expect(page.getByLabel("Dit nummer – det, kunderne ringer til")).toHaveValue(own);
  await page.getByLabel("Hvad slags abonnement er det?").selectOption("mobile");
  await page.getByRole("button", { name: "Gem nummer" }).click();
  await page.getByRole("button", { name: "Ring mig op med en kode" }).click();
  await expect(page.getByText(/Opkaldet er på vej/)).toBeVisible();
  const code = (await (await page.request.get(`/api/backend/dev/telephony/verification-code?workspace_id=${wsId}`, { headers: CSRF })).json()).code;
  await page.getByLabel("Koden").fill(code);
  await page.getByRole("button", { name: "Bekræft", exact: true }).click();
  const docs = page.getByRole("button", { name: "Send dokumentation" });
  await expect(docs.or(page.getByText("Nummeret er bekræftet.")).first()).toBeVisible();
  if (await docs.isVisible()) {
    await page.getByLabel("CVR-nummer").fill("12345678");
    await page.getByLabel("Adresse i Danmark").fill("Østergade 1, 8000 Aarhus C");
    await page.locator("input[type=file]").setInputFiles({ name: "cvr.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 cvr-udskrift") });
    await docs.click();
    await expect(docs).toHaveCount(0, { timeout: 15_000 });
  }
}

/** Confirm the subscription in the Betaling step (no Stripe here: that is the payment). */
async function pay(page: Page, wsId: string) {
  await page.getByRole("button", { name: "Bekræft abonnement" }).click();
  await expect(page.getByText(/Bekræftet · aftale v1/)).toBeVisible();
  const acc = await get(page, `/workspaces/${wsId}/billing/account`);
  test.skip(acc.configured, "Stripe er sat op i dette miljø: kortet (Stripe Checkout) køres ikke her");
  await expect(page.getByTestId("betaling-status")).toHaveText("Abonnementet er på plads. Nu kan Dialogbot gå live.");
}

test("Chat-kunde: hjemmeside → kanal Chat → viden → chat-widget → betaling → live; før betaling svarer widgetten ingen besøgende", async ({ page, browser }, info) => {
  test.setTimeout(240_000);
  const wsId = await signup(page, info, `Rebotti chat ${info.project.name} ${Date.now()}`);
  let srv = await serve(PORT, sitePage(`<p>Rebotti er en italiensk restaurant i Aarhus.</p>
    <footer>Rebotti ApS · Jægergårdsgade 10 · 8000 Aarhus C · CVR 12345674 · Ring på 70 12 34 56 · Man-fre 11-22</footer>`));
  servers.push(srv);

  // Virksomhed: the website first – it fills in the business
  await page.getByLabel("Hjemmesidens adresse").fill(`${SITE}/`);
  await page.getByRole("button", { name: /^Hent/ }).click();
  await expect(page.getByText(/Fundet på/)).toBeVisible({ timeout: 30_000 });
  // … then the channel: Chat only. The stepper shows only the relevant steps – no Telefon, no «sprunget over».
  await channels(page, { phone: false, chat: true });
  await expect(nav(page).getByRole("link", { name: /^Trin 3: Chat/ })).toBeVisible({ timeout: 15_000 });
  await expect(nav(page).getByRole("link", { name: /^Trin 4: Betaling/ })).toBeVisible();
  await expect(nav(page).getByRole("link", { name: /Telefon|Kalender|sprunget over/ })).toHaveCount(0);
  await page.getByLabel("Hvad I laver – én sætning").fill("Italiensk restaurant og take-away i Aarhus");
  await noOverflow(page);
  await shot(page, info, "kanal-chat-1-virksomhed");
  await page.getByRole("button", { name: "Videre til trin 2: Viden" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/viden$/, { timeout: 20_000 });
  // the website filled in phone and address by itself (nothing typed); chat only: the number is not required
  expect(await get(page, `/workspaces/${wsId}/profile`)).toMatchObject({ phone: "70 12 34 56", address_line: "Jægergårdsgade 10", postal_code: "8000", city: expect.stringMatching(/^Aarhus/) });

  // Viden: pasted text → suggestions → approve all
  await page.getByRole("button", { name: "Indsæt tekst" }).click();
  await page.getByLabel("Tekst med viden").fill(TEXT);
  await page.getByRole("button", { name: "Analysér teksten" }).click();
  await expect(page.getByTestId("import-summary")).toBeVisible({ timeout: 45_000 });
  const review = page.getByTestId("viden-review");
  await expect(review).toBeVisible({ timeout: 15_000 });
  await review.getByRole("button", { name: /^Godkend alle \(\d+\)$/ }).click();
  await expect(page.getByText(/ting er godkendt og bruges af Dialogbot/)).toBeVisible({ timeout: 15_000 });
  await expect(nav(page).getByRole("link", { name: /^Trin 2: Viden/ })).toHaveAccessibleName(/fuldført/);
  await shot(page, info, "kanal-chat-2-viden");
  await page.getByRole("link", { name: "Videre til trin 3: Chat" }).click();

  // Chat: widget (domain from the website), appearance (welcome), embed code, preview
  await expect(page).toHaveURL(/\/opsaetning\/chat$/);
  await expect(page.getByLabel("Jeres hjemmeside (domæne)")).toHaveValue(SITE);
  await page.getByLabel("Velkomst").fill("Ciao! Hvad kan vi hjælpe med?");
  await expect(page.getByRole("img", { name: "Sådan ser chatten ud på hjemmesiden" })).toContainText("Ciao! Hvad kan vi hjælpe med?");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByRole("status").getByText("Gemt", { exact: true })).toBeVisible();
  await expect(page.getByTestId("chat-live-when-paid")).toContainText("Chatten går live, når abonnementet er på plads");
  await expect(page.getByTestId("chat-live-when-paid").getByRole("link", { name: "Til betaling" })).toHaveAttribute("href", "/opsaetning/betaling");
  const preview = page.getByTestId("chat-preview");
  await preview.getByLabel("Skriv en besked til chatten").fill("Har I åbent om lørdagen?");
  await preview.getByRole("button", { name: "Send" }).click();
  await expect(preview.getByText("[fake] svar på: Har I åbent om lørdagen?")).toBeVisible({ timeout: 15_000 });
  await expect(nav(page).getByRole("link", { name: /^Trin 3: Chat/ })).toHaveAccessibleName(/fuldført/);
  await noOverflow(page);
  await shot(page, info, "kanal-chat-3-chat");
  const w = await get(page, `/workspaces/${wsId}/webchat`);
  expect(w.enabled).toBe(false);
  expect(w.allowed_origins).toEqual([SITE]);
  // nothing from the preview became a conversation
  expect((await get(page, `/workspaces/${wsId}/conversations`)).total).toBe(0);

  // Before payment: the embed code is on the website – and the visitor gets NO chat (backend-enforced)
  await close(srv); servers.splice(servers.indexOf(srv), 1);
  srv = await serve(PORT, sitePage(w.embed_code)); servers.push(srv);
  const visitor = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const before = await visitorSeesChat(page, visitor);
  expect(before.ok).toBe(false);
  expect(before.shown).toBe(false);
  await shot(before.site, info, "kanal-chat-4-besoegende-foer-betaling");
  await before.site.close();
  expect((await (await page.request.post(`${API}/api/v1/public/webchat/${w.widget_key}/conversations`, { headers: { origin: API }, data: { host_origin: SITE } })).json()).code).toBe("webchat_unavailable");
  // and switching it on through the API is refused
  const on = await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: w.version, enabled: true, greeting: w.greeting, allowed_origins: w.allowed_origins } });
  expect(on.status()).toBe(409);
  expect((await on.json()).code).toBe("subscription_required");

  // Betaling: a visible last step; «Gå live» waits for the subscription
  await page.getByRole("button", { name: "Videre til trin 4: Betaling" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/betaling$/);
  await expect(page.getByText("Trin 4 af 4 · sidste trin")).toBeVisible();
  await expect(page.getByText("Chatten går live, når abonnementet er på plads.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gå live" })).toBeDisabled();
  await noOverflow(page);
  await shot(page, info, "kanal-chat-5-betaling");
  await pay(page, wsId);
  await expect(page.getByRole("heading", { name: "Alt er klar – gå live" })).toBeVisible();
  await page.getByRole("button", { name: "Gå live" }).click();
  await expect(page).toHaveURL(/\/app\?taendt=1/, { timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "Webchatten er tændt" })).toBeVisible();
  await expect(page.getByTestId("setup-checklist")).toHaveCount(0); // everything done: no checklist on «I dag»
  await shot(page, info, "kanal-chat-6-live");

  // Live: the visitor gets the chat and an answer
  const after = await visitorSeesChat(page, visitor);
  expect(after.ok).toBe(true);
  await after.site.getByRole("button", { name: "Åbn chat" }).click();
  const chat = after.site.frameLocator('iframe[title^="Chat med"]');
  await expect(chat.getByText("Ciao! Hvad kan vi hjælpe med?")).toBeVisible();
  await chat.getByLabel("Din besked").fill("Kan man bestille bord?");
  await chat.locator("form:not(.contact)").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("[fake] svar på: Kan man bestille bord?")).toBeVisible({ timeout: 15_000 });
  await shot(after.site, info, "kanal-chat-7-besoegende-live");
  await visitor.close();
});

test("Telefon-kunde: telefon → nummer → betaling → forbind og prøveopkald → live; nummeret går ikke live før betaling", async ({ page }, info) => {
  test.setTimeout(240_000);
  const wsId = await signup(page, info, `Rebotti tlf ${info.project.name} ${Date.now()}`);
  const own = `+4520${String(Date.now()).slice(-6)}`;
  await channels(page, { phone: true, chat: false });
  await expect(nav(page).getByRole("link", { name: /^Trin 3: Telefon/ })).toBeVisible({ timeout: 15_000 });
  await expect(nav(page).getByRole("link", { name: /Chat|Kalender/ })).toHaveCount(0);
  // the phone is chosen up front, so the number is asked for in Virksomhed already
  await expect(page.getByText("Udfyld navn, telefonnummer og hvad I laver for at gå videre.")).toBeVisible();
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill(own);
  await page.getByLabel("Hvad I laver – én sætning").fill("Gulvafslibning og lakering i Aarhus");
  await page.getByLabel("Åbningstider").fill("Man–fre 07–16"); // approved at once: what the phone answers from
  await page.getByRole("button", { name: "Videre til trin 2: Viden" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/viden$/, { timeout: 20_000 });
  await page.getByRole("link", { name: "Videre til trin 3: Telefon" }).click();

  // Telefon: voice, number, forwarding
  await expect(page).toHaveURL(/\/opsaetning\/telefon$/);
  await expect(page.getByTestId("phone-live-when-paid")).toContainText("Telefonen går live, når abonnementet er på plads.");
  await page.getByRole("radio", { name: "Vælg" }).last().click();
  await expect(page.getByRole("radio", { name: "Valgt" })).toBeVisible();
  await phoneNumberInGuide(page, wsId, own);
  await expect(nav(page).getByRole("link", { name: /^Trin 3: Telefon/ })).toHaveAccessibleName(/fuldført/);
  await noOverflow(page);
  await shot(page, info, "kanal-tlf-1-telefon");
  expect((await get(page, `/workspaces/${wsId}/telephony`)).active).toBe(false);

  // Betaling: not paid → nothing goes live
  await page.getByRole("button", { name: "Videre til trin 4: Betaling" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/betaling$/);
  await expect(page.getByText("Telefonen går live, når abonnementet er på plads.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gå live" })).toBeDisabled();
  await shot(page, info, "kanal-tlf-2-betaling");
  await pay(page, wsId);
  // paid: connect the Dialogbot number and make the test call right here
  await page.getByRole("button", { name: "Forbind telefonen" }).click();
  await post(page, "/dev/operator/self");
  const t = await get(page, `/workspaces/${wsId}/telephony`);
  if (t.documents.required) await post(page, `/operator/telephony/workspaces/${wsId}/documents/review`, { status: "approved", note: "CVR-udskrift kontrolleret i E2E", regulatory_bundle_sid: "BU" + "e".repeat(32) });
  await post(page, `/operator/telephony/workspaces/${wsId}/jobs/run`);
  await page.reload();
  await page.getByRole("button", { name: "Start prøveopkald" }).click();
  await expect(page.getByText(/ring nu fra en anden telefon/)).toBeVisible(); // the test is waiting before the call comes
  await passTestCall(page, wsId, info);
  await page.reload();
  await expect(page.getByText(/Prøveopkaldet lykkedes \(simuleret\)/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alt er klar – gå live" })).toBeVisible();
  await noOverflow(page);
  await shot(page, info, "kanal-tlf-3-klar");
  await page.getByRole("button", { name: "Gå live" }).click();
  await expect(page).toHaveURL(/\/app\?taendt=1/, { timeout: 20_000 });
  await expect(page.getByText("Dialogbot er tændt").first()).toBeVisible();
  expect((await get(page, `/workspaces/${wsId}/telephony`)).active).toBe(true);
  await shot(page, info, "kanal-tlf-4-live");
});

test("Begge kanaler: Telefon og Chat i trinlinjen, tjeklisten følger med på I dag og i indstillinger, og begge går live efter betaling", async ({ page, browser }, info) => {
  test.setTimeout(240_000);
  const wsId = await signup(page, info, `Rebotti begge ${info.project.name} ${Date.now()}`);
  const own = `+4521${String(Date.now()).slice(-6)}`;
  await channels(page, { phone: true, chat: true });
  for (const [n, label] of [[1, "Virksomhed"], [2, "Viden"], [3, "Telefon"], [4, "Chat"], [5, "Betaling"]] as const) {
    await expect(nav(page).getByRole("link", { name: new RegExp(`^Trin ${n}: ${label}`) })).toBeVisible({ timeout: 15_000 });
  }
  await page.getByLabel("Hjemmesidens adresse").fill(`${SITE}/`);
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill(own);
  await page.getByLabel("Hvad I laver – én sætning").fill("Pizzeria i Aarhus");
  await page.getByRole("button", { name: "Videre til trin 2: Viden" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/viden$/, { timeout: 20_000 });
  // knowledge set up by hand (API) counts in the guide like anything else done outside it
  const item = await post(page, `/workspaces/${wsId}/knowledge/items`, { kind: "fact", title: "Åbent", content: { text: "Vi har åbent alle dage 11–22." } });
  await post(page, `/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`);

  // «Sæt op selv»: the checklist on «I dag» and in settings is the same truth as the stepper
  await page.getByRole("link", { name: "Sæt op selv" }).click();
  await expect(page).toHaveURL(/\/app\/indstillinger$/);
  const list = page.getByTestId("setup-checklist");
  await expect(list).toContainText("Guiden er ikke færdig · næste: Telefon");
  await expect(list.getByRole("link", { name: "Viden: klar" })).toBeVisible();
  await expect(list.getByRole("link", { name: "Chat: mangler" })).toBeVisible();
  await expect(list.getByText("Tilbage til guiden")).toBeVisible();
  await noOverflow(page);
  await shot(page, info, "kanal-begge-1-indstillinger");
  await page.goto("/app");
  await expect(page.getByTestId("setup-checklist")).toContainText("Opsætningen er ikke færdig · næste: Telefon");
  await page.getByTestId("setup-checklist").getByRole("link", { name: /Opsætningen er ikke færdig/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/telefon$/);
  await phoneNumberInGuide(page, wsId, own);
  await page.getByRole("button", { name: "Videre til trin 4: Chat" }).click();
  await expect(page).toHaveURL(/\/opsaetning\/chat$/);
  await expect(page.getByLabel("Jeres hjemmeside (domæne)")).toHaveValue(SITE);
  await page.getByRole("button", { name: "Videre til trin 5: Betaling" }).click(); // saves the domain first
  await expect(page).toHaveURL(/\/opsaetning\/betaling$/);
  expect((await get(page, `/workspaces/${wsId}/webchat`)).allowed_origins).toEqual([SITE]);

  // set up, not paid: I dag shows the last step, the guide says both go live after payment
  await expect(page.getByText("Telefon og chat går live, når abonnementet er på plads.")).toBeVisible();
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app$/); // set up: no longer sent into the guide
  await expect(page.getByTestId("setup-checklist")).toContainText("Dialogbot er sat op · vælg abonnement og betaling");
  await page.getByTestId("setup-checklist").getByRole("link", { name: /vælg abonnement og betaling/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/betaling$/);
  await pay(page, wsId);
  await page.getByRole("button", { name: "Forbind telefonen" }).click();
  await post(page, "/dev/operator/self");
  const t = await get(page, `/workspaces/${wsId}/telephony`);
  if (t.documents.required) await post(page, `/operator/telephony/workspaces/${wsId}/documents/review`, { status: "approved", note: "CVR-udskrift kontrolleret i E2E", regulatory_bundle_sid: "BU" + "e".repeat(32) });
  await post(page, `/operator/telephony/workspaces/${wsId}/jobs/run`);
  await page.reload();
  await page.getByRole("button", { name: "Start prøveopkald" }).click();
  await expect(page.getByText(/ring nu fra en anden telefon/)).toBeVisible(); // the test is waiting before the call comes
  await passTestCall(page, wsId, info);
  await page.reload();
  // paid but not live yet: I dag says «gå live»
  await page.goto("/app");
  await expect(page.getByTestId("setup-checklist")).toContainText("Abonnementet er på plads · gå live");
  await page.goto("/opsaetning/betaling");
  await expect(page.getByRole("heading", { name: "Alt er klar – gå live" })).toBeVisible();
  await noOverflow(page);
  await shot(page, info, "kanal-begge-2-klar");
  await page.getByRole("button", { name: "Gå live" }).click();
  await expect(page).toHaveURL(/\/app\?taendt=1/, { timeout: 20_000 });
  expect((await get(page, `/workspaces/${wsId}/telephony`)).active).toBe(true);
  const w = await get(page, `/workspaces/${wsId}/webchat`);
  expect(w.enabled && w.available).toBe(true);
  await expect(page.getByTestId("setup-checklist")).toHaveCount(0);
  await page.goto("/app/indstillinger");
  await expect(page.getByTestId("setup-checklist")).toHaveCount(0);
  // the visitor gets the chat now
  servers.push(await serve(PORT, sitePage(w.embed_code)));
  const visitor = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const seen = await visitorSeesChat(page, visitor);
  expect(seen.ok).toBe(true);
  await visitor.close();
  await shot(page, info, "kanal-begge-3-live");
});
