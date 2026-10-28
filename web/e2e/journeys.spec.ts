import { expect, test } from "@playwright/test";
import { CUSTOMER_SITE, DEMO_PASSWORD, PREVIEW_CODE, SEEDED, serve, freshOwner, latestMailLink, login, shot, uniqueEmail } from "./helpers";

/* The eight core journeys of milestone A. Blueprint §9.1 is not in the repository; these cover the flows that
 * exist today (A01–A06, O01–O04, K03–K05, G01/G05, S02/S08/S09) and assert the honesty rules along the way. */

test("1 · A01→A03→A06: tilmelding med bevaret hensigt, bekræftelse og første arbejdsrum", async ({ page }, info) => {
  const email = uniqueEmail("signup", info);
  await page.goto("/");
  await expect(page).toHaveURL(/\/preview$/); // PREVIEW_GATE=on in CI: the front page is behind P00
  await page.getByLabel("Invitationskode").fill("forkert-kode-123");
  await page.getByRole("button", { name: "Lås op og se forsiden" }).click();
  await expect(page.getByText("Koden er ikke gyldig.", { exact: false })).toBeVisible();
  await page.getByLabel("Invitationskode").fill(PREVIEW_CODE.toLowerCase());
  await page.getByRole("button", { name: "Lås op og se forsiden" }).click();
  // Indgang: two doors – hear it (/proev) or read how it is built (/byggevejledning).
  await expect(page.getByRole("heading", { name: "Hvor vil du starte?" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Hør den først/ })).toHaveAttribute("href", "/proev");
  await expect(page.getByRole("link", { name: /Se, hvordan den bygges/ })).toHaveAttribute("href", "/byggevejledning");
  await shot(page, info, "p01-indgang");
  // Vej A: the chat on /proev asks the backend first and is honest – no sales workspace is configured in CI, so it
  // cannot ring anyone and says so instead of pretending a call was placed.
  const demoInfo = page.waitForResponse((r) => r.url().includes("/demo-call") && r.request().method() === "GET");
  await page.getByRole("link", { name: /Hør den først/ }).click();
  await expect(page).toHaveURL(/\/proev$/);
  await demoInfo;
  const log = page.getByRole("log");
  await expect(log.getByText(/Hej! Jeg hedder Peter og er Dialogbots digitale receptionist/)).toBeVisible();
  await page.getByRole("button", { name: "Ja, ring til mig" }).click();
  await expect(log.getByText(/Prøveopkaldet aktiveres snart – indtil da ringer vi til dig manuelt/)).toBeVisible();
  await expect(page.getByText("Ikke lige nu")).toBeVisible(); // step label
  await expect(page.getByRole("button", { name: "Ring mig op" })).toHaveCount(0); // no number is ever asked for
  await expect(page.getByRole("link", { name: "Ring til os" })).toBeVisible();
  await shot(page, info, "p06-proev-chat");
  // Vej B: the byggevejledning offers the bricks; the campaigns brick starts signup with the intent preserved.
  await page.getByRole("link", { name: "Se byggevejledningen" }).click();
  await expect(page).toHaveURL(/\/byggevejledning$/);
  await expect(page.getByRole("heading", { name: "Vælg de klodser, du har brug for" })).toBeVisible();
  await page.getByRole("link", { name: "Start med kundeopfølgning" }).click();
  await expect(page).toHaveURL(/\/signup\?intent=campaigns/);
  await page.getByLabel("Dit navn").fill("E2E Tilmelding");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await expect(page.getByLabel("Jeg vil starte med")).toHaveValue("campaigns");
  await shot(page, info, "a01-signup");
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/verify-email/);
  await shot(page, info, "a03-afventer");
  const link = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  await page.goto(link);
  await expect(page.getByText("Din e-mail er bekræftet.")).toBeVisible();
  await page.getByRole("link", { name: /Fortsæt til arbejdsrum/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/1/);
  await page.getByLabel("Navn (som den siger det)").fill("E2E Kampagne ApS");
  await shot(page, info, "a06-opret");
  await page.getByRole("button", { name: "Videre" }).click();
  // The workspace exists now; the intent from sign-up («kampagner») is kept as the chosen card.
  await expect(page.getByLabel("Navn (som den siger det)")).toHaveValue("E2E Kampagne ApS");
  await expect(page.getByRole("checkbox", { name: /Ringe kunder op/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /Tage telefonen/ })).not.toBeChecked();
});

test("2 · A02: forkert adgangskode afvises, login husker destination, log ud", async ({ page }, info) => {
  await page.goto("/app/viden");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fviden/);
  await page.getByLabel("E-mail").fill(SEEDED.owner);
  await page.getByLabel("Adgangskode", { exact: true }).fill("forkert-kode-123");
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await shot(page, info, "a02-fejl");
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/app\/viden/);
  await page.goto("/app/konto/profil");
  await expect(page.getByText("Denne enhed")).toBeVisible();
  await shot(page, info, "s08-profil");
  await page.getByRole("button", { name: "Log ud" }).first().click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/app/setup");
  await expect(page).toHaveURL(/\/login/);
});

test("3 · A04: nulstil adgangskode via link og log ind med den nye", async ({ page }, info) => {
  const { email } = await freshOwner(page, info);
  await page.goto("/password/forgot");
  await page.getByLabel("E-mail").fill(email);
  await page.getByRole("button", { name: "Send nulstillingslink" }).click();
  await expect(page.getByText(/Hvis adressen findes/)).toBeVisible();
  const link = await latestMailLink(page.request, /\/password\/reset\?token=[\w-]+/);
  await page.goto(link);
  const next = "Ny-Kode-2026!";
  await page.getByLabel("Ny adgangskode", { exact: true }).fill(next);
  await expect(page.getByText("Mindst 10 tegn")).toBeVisible();
  await page.getByLabel("Bekræft ny adgangskode").fill(next);
  await shot(page, info, "a04-ny-kode");
  await page.getByRole("button", { name: /Gem ny adgangskode/ }).click();
  await expect(page).toHaveURL(/\/login\?reset=1/);
  await login(page, email, next);
  await expect(page).toHaveURL(/\/app/);
});

test("4 · Trin 1: virksomhed, mål og sprog gemmes løbende og står der igen", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill("+4586123456");
  await page.getByLabel(/^Hvad I laver/).fill("Gulvafslibning i Storkøbenhavn");
  await page.getByLabel("Åbningstider").fill("Man–fre 07–16");
  await page.getByLabel("Hvor I kører").fill("Storkøbenhavn, Nordsjælland");
  await page.getByRole("checkbox", { name: /Booke aftaler/ }).check();
  await page.getByRole("button", { name: "Engelsk" }).click();
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await shot(page, info, "trin1-udfyldt");
  await page.reload();
  await expect(page.getByLabel("Telefonnummer, kunderne ringer til")).toHaveValue("+4586123456");
  await expect(page.getByLabel(/^Hvad I laver/)).toHaveValue("Gulvafslibning i Storkøbenhavn");
  await expect(page.getByLabel("Åbningstider")).toHaveValue("Man–fre 07–16");
  await expect(page.getByLabel("Hvor I kører")).toHaveValue("Storkøbenhavn, Nordsjælland");
  await expect(page.getByRole("checkbox", { name: /Booke aftaler/ })).toBeChecked();
  await expect(page.getByRole("button", { name: "Engelsk" })).toHaveAttribute("aria-pressed", "true");
  // Hours are real knowledge: approved and live straight away, not a draft waiting somewhere.
  const ws = (await (await page.request.get("/api/backend/workspaces")).json())[0].id;
  const live = await (await page.request.get(`/api/backend/workspaces/${ws}/assistant/knowledge`)).json();
  expect(JSON.stringify(live.items)).toContain("07:00");
  // The next step follows the choice: booking was chosen, so trin 2 comes before trin 3.
  await page.getByRole("button", { name: /Videre til trin 2/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/2/);
});

test("5 · Viden: ejerens nye ydelse gælder med det samme og Dialogbot siger den højt; en medarbejders forslag venter på godkendelse", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/viden");
  await expect(page.getByText(/0 godkendte emner/)).toBeVisible();
  await page.getByRole("button", { name: "Tilføj en ydelse" }).click();
  await page.getByLabel("Hvad hedder den?").fill("Standard gulvafslibning");
  await page.getByLabel("Pris (som kunden skal høre den)").fill("fra 145 kr. pr. m²");
  await page.getByLabel("Hvad skal den sige bagefter?").fill("Afslibning og 2x lak");
  await page.getByRole("button", { name: "Gem – og vis mig, hvordan den siger det" }).click();
  await expect(page.getByText(/Sådan svarer den på «Hvad koster Standard gulvafslibning\?»/)).toBeVisible();
  await expect(page.getByText(/\[fake\] svar på/).first()).toBeVisible();
  await shot(page, info, "viden-ny-ydelse");
  await page.reload();
  const row = page.getByRole("listitem").filter({ hasText: "Standard gulvafslibning" });
  await expect(row.getByText("145,-")).toBeVisible();
  await expect(row.getByText("Sælger", { exact: true })).toBeVisible();
  const live = await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json();
  expect(JSON.stringify(live.items)).toContain("Standard gulvafslibning");
  // «Ret»: the price is changed in place and is live at once.
  await row.getByRole("button", { name: "Ret", exact: true }).click();
  await page.getByLabel("Pris (ekskl. moms)").fill("165");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByText("Gemt – Dialogbot bruger det nu")).toBeVisible();

  // A colleague who may not approve sends a proposal; the owner approves it.
  const stamp = `Forslag ${Date.now()}`;
  await page.context().clearCookies();
  await login(page, SEEDED.staff);
  await page.goto("/app/viden");
  await page.getByRole("button", { name: "Tilføj en ydelse" }).click();
  await page.getByLabel("Hvad hedder den?").fill(stamp);
  await page.getByLabel("Pris (som kunden skal høre den)").fill("500 kr.");
  await page.getByRole("button", { name: "Send til godkendelse" }).click();
  await expect(page.getByText(/Sendt til godkendelse hos en ejer eller administrator/)).toBeVisible();
  await page.context().clearCookies();
  await login(page, SEEDED.owner);
  await page.goto("/app/viden");
  const card = page.locator("div").filter({ hasText: stamp }).filter({ has: page.getByRole("button", { name: "Godkend", exact: true }) }).last();
  await expect(card.getByText(/Dialogbot foreslår/)).toBeVisible();
  await shot(page, info, "viden-forslag");
  await card.getByRole("button", { name: "Godkend", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: stamp })).toBeVisible();
});

test("6 · Opsætningen kommer først: /app og gamle adresser sender et ufærdigt arbejdsrum til trin 1; «senere» slipper igennem", async ({ page, context }, info) => {
  await login(page, SEEDED.owner);
  await context.clearCookies({ name: "db_setup_later" });
  await page.goto("/app");
  await expect(page).toHaveURL(/\/opsaetning\/1/);
  for (const old of ["/app/setup", "/onboarding/business", "/onboarding/goals", "/onboarding/languages", "/onboarding/workspace", "/app/settings/business"]) {
    await page.goto(old);
    await expect(page, old).toHaveURL(/\/opsaetning\/1/);
  }
  // Stepper: three steps, the current one marked.
  await expect(page.getByRole("link", { name: /Virksomhed/ })).toHaveAttribute("aria-current", "step");
  await shot(page, info, "g01-trin1");
  await page.goto("/opsaetning/3");
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toBeDisabled();
  await expect(page.getByText(/Mangler: .*bekræft jeres nummer/)).toBeVisible();
  // «Jeg gør resten senere» lets people look around; I dag then says it is not finished and never claims an active AI.
  await page.goto("/opsaetning/1");
  await page.evaluate(() => { document.cookie = "db_setup_later=1; path=/"; });
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText(/Opsætningen er ikke færdig/)).toBeVisible();
  await expect(page.getByText(/Aktiv AI|AI Live/)).toHaveCount(0);
  await page.goto("/app/not-yet?area=Kampagner");
  await expect(page).toHaveURL(/\/app\/hjaelp/);
});

test("7 · S02→A05: ejer inviterer, kollega accepterer og lander i arbejdsrummet", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const invitee = uniqueEmail("invitee", info);
  await page.goto("/app/konto");
  await page.getByLabel("Invitér med e-mail").fill(invitee);
  await page.getByLabel("Må", { exact: true }).selectOption("staff");
  await page.getByRole("button", { name: "Invitér", exact: true }).click();
  await expect(page.getByText(invitee)).toBeVisible();
  await shot(page, info, "s02-team");

  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: page.viewportSize() ?? undefined });
  const p2 = await ctx.newPage();
  const CSRF = { "x-requested-with": "dialogbot" };
  expect((await p2.request.post("/api/backend/auth/register", { headers: CSRF, data: { email: invitee, password: DEMO_PASSWORD, display_name: "E2E Kollega", signup_intent: "reception" } })).status()).toBe(201);
  await p2.request.post("/api/auth/login", { headers: CSRF, data: { email: invitee, password: DEMO_PASSWORD } });
  const link = await latestMailLink(p2.request, /\/invite\/[\w-]+/);
  await p2.goto(link);
  await expect(p2.getByText("Afventer svar")).toBeVisible();
  await shot(p2, info, "a05-invitation");
  await p2.getByRole("button", { name: "Acceptér invitation" }).click();
  await expect(p2).toHaveURL(/\/opsaetning\/1/);
  const list = await (await p2.request.get("/api/backend/workspaces")).json();
  expect(list.map((w: { id: string }) => w.id)).toContain(wsId);
  await ctx.close();
});

test("8 · Roller: læser kan ikke redigere, medarbejder kan ikke se aktivitetslog, admin kan", async ({ page }, info) => {
  await login(page, SEEDED.reader);
  await page.goto("/opsaetning/1");
  await expect(page.getByText(/Din rolle \(læser\)/)).toBeVisible();
  await page.getByText("CVR og adresse (valgfrit)").click();
  await expect(page.getByLabel("By")).toBeDisabled();
  await expect(page.getByLabel(/^Hvad I laver/)).toBeDisabled();
  await page.goto("/app/viden");
  await expect(page.getByRole("heading", { name: "Det I sælger" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tilføj en ydelse" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Ret", exact: true })).toHaveCount(0);
  await shot(page, info, "roller-laeser");
  await page.context().clearCookies();
  await login(page, SEEDED.staff);
  await page.goto("/app/indstillinger/log");
  await expect(page.getByText(/kun ses af ejere og administratorer/)).toBeVisible();
  await page.context().clearCookies();
  await login(page, SEEDED.admin);
  await page.goto("/app/indstillinger/log");
  await expect(page.getByRole("heading", { name: "Aktivitetslog" })).toBeVisible();
  await shot(page, info, "s09-log");
});

test("9 · Test som kunde: medarbejder tester assistenten mod godkendt viden fra Det ved den", async ({ page }, info) => {
  await login(page, SEEDED.staff);
  await page.goto("/app/viden");
  const narrow = (page.viewportSize()?.width ?? 1440) < 1280;
  if (narrow) await page.getByRole("button", { name: "Ændr noget" }).click();
  await page.getByRole("button", { name: "Test mig som kunde" }).filter({ visible: true }).click();
  const ask = page.getByLabel("Skriv et spørgsmål, som en kunde ville stille").filter({ visible: true });
  await ask.fill("Hvad koster afslibning?");
  await page.keyboard.press("Enter");
  await expect(page.getByText("[fake] svar på: Hvad koster afslibning?").filter({ visible: true }).first()).toBeVisible();
  await shot(page, info, "test-som-kunde");
});

test("10 · P00: forsiden er skjult bag forhåndskode; venteliste; invitationslink virker uden kode", async ({ page }, info) => {
  await page.goto("/signup");
  await expect(page).toHaveURL(/\/preview\?next=%2Fsignup/);
  await expect(page.getByRole("heading", { name: "Skriv dig op til tidlig adgang" })).toBeVisible();
  await shot(page, info, "p00-adgang");
  await page.getByLabel("Din arbejds-e-mail").fill(uniqueEmail("venteliste", info));
  await page.getByLabel("Virksomhedstype").selectOption("craft");
  await page.getByRole("button", { name: "Opfølgning på tilbud" }).click();
  await expect(page.getByRole("button", { name: "Opfølgning på tilbud" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("checkbox", { name: /I må skrive til mig/ }).check();
  await page.getByRole("button", { name: "Skriv mig på ventelisten" }).click();
  await expect(page.getByText("Tak – du står på ventelisten.")).toBeVisible();
  await shot(page, info, "p00-venteliste-tak");
  await page.goto("/privatliv");
  await expect(page.getByText("Abildgade 18, 8200 Aarhus, Danmark").first()).toBeVisible();
  // Colleagues invited by e-mail must reach signup without a preview code.
  await page.goto("/signup?next=/invite/abc");
  await expect(page).toHaveURL(/\/signup\?next=/);
  await expect(page.getByRole("button", { name: "Opret konto" })).toBeVisible();
});

const servers: import("node:http").Server[] = [];
test.afterEach(() => { servers.splice(0).forEach((s) => s.close()); });

test("11 · W01: ejer slår webchat til, kunde chatter på eget domæne, samtalen lander i indbakken", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "service", title: "Gulvafslibning", content: { price_net_minor: 14500 } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();

  await page.goto("/app/indstillinger/webchat");
  await expect(page.getByText("Testmiljø: svarene kommer fra en simuleret model")).toBeVisible();
  await page.getByRole("switch", { name: "Vis widgetten på hjemmesiden" }).check();
  await page.getByLabel("Godkendte domæner").fill(CUSTOMER_SITE);
  await page.getByRole("button", { name: "Gem indstillinger" }).click();
  await expect(page.getByText("Aktiv på jeres domæner")).toBeVisible();
  const embed = await page.getByLabel("Indlejringskode").textContent();
  expect(embed).toContain("data-dialogbot-key=");
  await shot(page, info, "w01-webchat");

  // The customer's own website on another origin, with the embed code pasted in.
  // Served by a real local server (not page.route): Chromium's private-network rules treat routed pages as "unknown".
  const html = (body: string) => `<!doctype html><html lang="da"><head><title>Kundeside</title></head><body>${body}${embed}</body></html>`;
  servers.push(await serve(4000, html("<h1>Fjord Gulv</h1>")), await serve(4001, html("<h1>Anden side</h1>")));
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const site = await ctx.newPage();
  await site.goto(`${CUSTOMER_SITE}/`);
  await site.getByRole("button", { name: "Åbn chat" }).click();
  const chat = site.frameLocator('iframe[title^="Chat med"]');
  await expect(chat.getByText(/digitale assistent/).first()).toBeVisible();
  await expect(chat.getByText("Du skriver med en AI-assistent.", { exact: false })).toBeVisible();
  await chat.getByLabel("Din besked").fill("Hvad koster gulvafslibning?");
  await chat.getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("[fake] svar på: Hvad koster gulvafslibning?")).toBeVisible();
  await shot(site, info, "w01-kundeside-chat");
  await ctx.close();

  // Another website may not embed the widget: no launcher appears.
  const other = await browser.newContext();
  const evil = await other.newPage();
  await evil.goto("http://localhost:4001/");
  await expect(evil.getByRole("heading", { name: "Anden side" })).toBeVisible();
  await evil.waitForTimeout(1500);
  await expect(evil.getByRole("button", { name: "Åbn chat" })).toHaveCount(0);
  await other.close();

  await page.goto("/app/opkald");
  await page.getByRole("link", { name: /Hvad koster gulvafslibning\?/ }).click();
  await expect(page.getByText("[fake] svar på: Hvad koster gulvafslibning?")).toBeVisible();
  await shot(page, info, "opkald-samtale");
  // «Ugen» counts it and lists the question as a topic Dialogbot could answer.
  await page.goto("/app/ugen");
  await expect(page.getByRole("heading", { name: "Sådan gik ugen" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Hvad koster gulvafslibning?" })).toBeVisible();
  await expect(page.getByText("Ja", { exact: true }).first()).toBeVisible();
  await shot(page, info, "ugen");
});

test("12 · Henvendelse: kunde beder om kontakt i webchat, ejer kvalificerer, bekræfter abonnementet, godkender og løser opgaven", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "service", title: "Gulvafslibning", content: { price_net_minor: 14500 } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF });
  const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/webchat`)).json();
  const w = await (await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: s.version, enabled: true, allowed_origins: [CUSTOMER_SITE], greeting: "" } })).json();
  servers.push(await serve(4000, `<!doctype html><html lang="da"><head><title>Kundeside</title></head><body><h1>Fjord Gulv</h1>${w.embed_code}</body></html>`));

  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const site = await ctx.newPage();
  await site.goto(`${CUSTOMER_SITE}/`);
  await site.getByRole("button", { name: "Åbn chat" }).click();
  const chat = site.frameLocator('iframe[title^="Chat med"]');
  await chat.getByLabel("Din besked").fill("Kan I slibe 65 m² plankegulv?");
  await chat.locator("form:not(.contact)").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("[fake] svar på: Kan I slibe 65 m² plankegulv?")).toBeVisible();
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  await chat.locator("form.contact").getByLabel("Navn").fill("Henrik Villumsen");
  await chat.locator("form.contact").getByLabel("E-mail").fill("henrik@example.com");
  await chat.locator("form.contact").getByLabel("Telefon").fill("+45 20 30 40 50");
  const windowLabel = await chat.locator("form.contact").getByLabel("Hvornår må vi ringe?").locator("option").last().textContent();
  await chat.locator("form.contact").getByLabel("Hvornår må vi ringe?").selectOption({ label: windowLabel ?? "" });
  await chat.locator("form.contact").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("Sæt flueben, så virksomheden må kontakte dig.")).toBeVisible(); // consent is required
  await chat.locator("form.contact").getByLabel("Virksomheden må kontakte mig", { exact: false }).check();
  await chat.locator("form.contact").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("Tak, Henrik Villumsen!", { exact: false })).toBeVisible();
  await shot(site, info, "kontakt-i-webchat");
  await ctx.close();

  await page.goto("/app/opkald?f=to_you");
  await page.getByRole("link", { name: /Henrik Villumsen/ }).click();
  await page.getByRole("link", { name: "Åbn henvendelse" }).click();
  await expect(page.getByRole("heading", { name: "Henrik Villumsen" })).toBeVisible();
  await expect(page.getByText(`Ring Henrik Villumsen op – ${windowLabel}`)).toBeVisible();
  await expect(page.getByText(/Ønsker opkald/)).toBeVisible();
  await expect(page.getByText("Abonnementet er ikke bekræftet endnu", { exact: false }).first()).toBeVisible();
  await page.getByLabel("Kvalificering").selectOption("qualified");
  await page.getByLabel("Forløb").selectOption("contacted");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByLabel("Kvalificering")).toHaveValue("qualified");

  await page.goto("/app/konto");
  await page.getByRole("button", { name: "Bekræft abonnement" }).click();
  await expect(page.getByText(/Bekræftet · aftale v1/)).toBeVisible();
  await expect(page.getByText("2.495,00 kr.").first()).toBeVisible(); // one offer: from 2.495 kr./md. ekskl. moms
  await shot(page, info, "prisaftale");

  await page.goBack();
  await page.reload();
  await page.getByRole("button", { name: "Godkend henvendelse" }).click();
  await expect(page.getByText("Ingen pris pr. henvendelse", { exact: false }).first()).toBeVisible(); // no fee per enquiry
  await expect(page.getByLabel("Kvalificering")).toBeDisabled();
  await page.getByRole("checkbox", { name: /Færdig: Ring Henrik Villumsen op/ }).check();
  await expect(page.getByRole("checkbox", { name: /Færdig: Ring Henrik Villumsen op/ })).toBeChecked();
  await shot(page, info, "henvendelse-godkendt");
  await page.getByRole("link", { name: "Se samtalen" }).click();
  await expect(page.getByText("Kan I slibe 65 m² plankegulv?").first()).toBeVisible();
});

test("13 · Ugen: ugens tal og emner, uge-vælger, og dagsrapporten kan ændres", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/ugen");
  await expect(page.getByRole("heading", { name: "Sådan gik ugen" })).toBeVisible();
  await expect(page.getByText("opkald og beskeder besvaret")).toBeVisible();
  await expect(page.getByRole("list", { name: "Opkald pr. dag" }).getByRole("listitem")).toHaveCount(7);
  await expect(page.getByText("Ingen spørgsmål i denne uge.")).toBeVisible();
  await page.getByRole("link", { name: /^‹ Uge \d+/ }).click();
  await expect(page).toHaveURL(/uge=\d{4}-\d{2}-\d{2}/);
  await expect(page.getByRole("link", { name: "Denne uge" })).toBeVisible();
  await page.getByRole("link", { name: "Denne uge" }).click();
  await page.getByText("Ret selv").click();
  await page.getByLabel("Klokken").selectOption("6");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Gemt" })).toBeVisible();
  await shot(page, info, "ugen-tom");
  await page.reload();
  await expect(page.getByText(/kl\. 06/)).toBeVisible();
});

test("14 · S03: ny kunde sætter telefonen op uden leverandørkonti – nummer, kontrolkode, dokumentation, Dialogbot-nummer, prøveopkald, aktivering; opkald bliver til samtale, henvendelse og opgave", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const post = async (path: string, data: unknown = {}) => {
    const r = await page.request.post(`/api/backend${path}`, { headers: CSRF, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  const item = await post(`/workspaces/${wsId}/knowledge/items`, { kind: "service", title: "Gulvafslibning", content: { price_net_minor: 14500 } });
  await post(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`);
  await post(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`);
  await post(`/workspaces/${wsId}/agreement`, { model: "A" });
  const own = `+4520${String(Date.now()).slice(-6)}`;

  await page.goto("/app/indstillinger/telefoni");
  await expect(page.getByText("Ikke sat op", { exact: true })).toBeVisible();
  const text = await page.locator("main").innerText();
  for (const word of ["Vapi", "Twilio", "webhook", "Server URL", "Bearer", "API-nøgle", "nummer-id"]) expect(text).not.toContain(word);
  await page.getByLabel("Virksomhedens telefonnummer").fill(own);
  await page.getByLabel("Hvilken type abonnement er det?").selectOption("mobile");
  await page.getByRole("button", { name: "Gem nummer" }).click();
  await expect(page.getByText("Afventer oplysninger", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Ring mig op med en kode" }).click();
  await expect(page.getByText(/Opkaldet er på vej/)).toBeVisible();
  const code = (await (await page.request.get(`/api/backend/dev/telephony/verification-code?workspace_id=${wsId}`, { headers: CSRF })).json()).code;
  await page.getByLabel("Kode", { exact: true }).fill(code);
  await page.getByRole("button", { name: "Bekræft", exact: true }).click();
  await expect(page.getByText(`${own} er bekræftet.`)).toBeVisible();
  await page.getByLabel("CVR-nummer").fill("12345678");
  await page.getByLabel("Adresse i Danmark").fill("Østergade 1, 8000 Aarhus C");
  await page.locator("input[type=file]").setInputFiles({ name: "cvr.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 cvr-udskrift") });
  await page.getByRole("button", { name: "Gem virksomhedsoplysninger" }).click();
  await expect(page.getByText(/Sendt – Dialogbot gennemgår/)).toBeVisible();
  await page.getByRole("button", { name: "Forbind telefonen" }).click();
  await expect(page.getByText("Forbindelse klargøres", { exact: true })).toBeVisible();
  await expect(page.getByText(/gennemgår jeres virksomhedsdokumentation/).first()).toBeVisible();
  // Dialogbot's operator reviews the documentation and the job buys and connects the number (simulated provider)
  await post("/dev/operator/self");
  await post(`/operator/telephony/workspaces/${wsId}/documents/review`, { status: "approved", note: "CVR-udskrift kontrolleret i E2E", regulatory_bundle_sid: "BU" + "e".repeat(32) });
  await post(`/operator/telephony/workspaces/${wsId}/jobs/run`);
  await page.reload();
  await expect(page.getByText("Klar til prøveopkald", { exact: true })).toBeVisible();
  const dest = (await (await page.request.get(`/api/backend/workspaces/${wsId}/telephony`)).json()).destination.e164 as string;
  await expect(page.getByText(`**61*${dest}#`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Aktivér telefonen" })).toBeDisabled();
  await shot(page, info, "s03-telefoni-guide");
  await page.getByRole("button", { name: "Start prøveopkald" }).click();
  await expect(page.getByText(/Venter på opkaldet/)).toBeVisible();

  const api = process.env.API_BASE_URL ?? "http://localhost:8000";
  const auth = { authorization: `Bearer ${process.env.VAPI_SERVER_SECRET ?? "e2e-only-vapi-secret-0123456789"}` };
  const callId = `call_${info.project.name}_${Date.now()}`;
  const req = await page.request.post(`${api}/api/v1/webhooks/vapi`, { headers: auth, data: { message: { type: "assistant-request", call: { id: callId, customer: { number: "+4540404040" } }, phoneNumber: { number: dest } } } });
  const assistant = (await req.json()).assistant;
  expect(assistant.firstMessage).toContain("Dette er et prøveopkald");
  expect(assistant.model.messages[0].content).toContain("Gulvafslibning");
  expect(assistant.transcriber.language).toBe("da");
  const report = await page.request.post(`${api}/api/v1/webhooks/vapi`, { headers: auth, data: { message: {
    type: "end-of-call-report", endedReason: "customer-ended-call", analysis: { summary: "Vil have tilbud på afslibning." },
    phoneNumber: { number: dest },
    call: { id: callId, customer: { number: "+4520304050" }, startedAt: new Date(Date.now() - 65_000).toISOString(), endedAt: new Date().toISOString() },
    artifact: { messages: [{ role: "bot", message: "Hej, du har ringet til os." }, { role: "user", message: "Hvad koster afslibning?" }] } } } });
  expect((await report.json()).outcome).toBe("applied");
  await page.reload();
  await expect(page.getByText(/Prøveopkaldet ramte jeres assistent.*\(Simuleret\)/)).toBeVisible();
  await page.getByRole("button", { name: "Aktivér telefonen" }).click();
  await expect(page.getByText("Aktiv", { exact: true })).toBeVisible();
  await expect(page.getByText("Vil have tilbud på afslibning.")).toBeVisible();
  await shot(page, info, "s03-telefoni-aktiv");
  await page.goto("/app/operator/telephony");
  await expect(page.getByRole("heading", { name: "Telefoni: leverandører, klargøring og numre" })).toBeVisible();
  await shot(page, info, "operator-telefoni");
  await page.goto("/app/opkald");
  await page.getByRole("link", { name: /Vil have tilbud på afslibning/ }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Hvad koster afslibning?" }).first()).toBeVisible();   // the transcript
  await page.getByRole("link", { name: "Åbn henvendelse" }).click();
  await expect(page.getByText("Ring tilbage til +4520304050")).toBeVisible();
  await shot(page, info, "telefon-henvendelse");
});

test("15 · Medarbejder overtager en webchat, svarer kunden, og assistenten holder pause", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "service", title: "Gulvafslibning", content: {} } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF });
  const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/webchat`)).json();
  const w = await (await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: s.version, enabled: true, allowed_origins: [CUSTOMER_SITE], greeting: "" } })).json();
  servers.push(await serve(4000, `<!doctype html><html lang="da"><head><title>Kundeside</title></head><body><h1>Fjord Gulv</h1>${w.embed_code}</body></html>`));

  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const site = await ctx.newPage();
  await site.goto(`${CUSTOMER_SITE}/`);
  await site.getByRole("button", { name: "Åbn chat" }).click();
  const chat = site.frameLocator('iframe[title^="Chat med"]');
  const send = chat.locator("form:not(.contact)").getByRole("button", { name: "Send" });
  await chat.getByLabel("Din besked").fill("Må jeg tale med en person?");
  await send.click();
  await expect(chat.getByText("[fake] svar på: Må jeg tale med en person?")).toBeVisible();

  await page.goto("/app/opkald");
  await page.getByRole("link", { name: /Må jeg tale med en person\?/ }).click();
  await expect(page).toHaveURL(/\/app\/opkald\/[0-9a-f-]{36}/);
  await page.getByLabel("Svar kunden i chatten").filter({ visible: true }).fill("Hej, det er Mads fra Fjord. Hvad drejer det sig om?");
  await page.getByRole("button", { name: "Send svar" }).click();
  await expect(page.getByText("En medarbejder har overtaget samtalen", { exact: false })).toBeVisible();

  await expect(chat.getByText("Hej, det er Mads fra Fjord.", { exact: false })).toBeVisible({ timeout: 15_000 }); // widget polls
  await chat.getByLabel("Din besked").fill("Kan I komme onsdag?");
  await send.click();
  await expect(chat.getByText("En medarbejder svarer dig her i chatten.")).toBeVisible();
  await expect(chat.getByText("[fake] svar på: Kan I komme onsdag?")).toHaveCount(0);
  await shot(site, info, "webchat-medarbejder");
  await ctx.close();

  await expect(page.getByText("Kan I komme onsdag?")).toBeVisible({ timeout: 15_000 }); // inbox auto-refresh
  await shot(page, info, "opkald-overtaget");
  await page.goto("/app/opkald?f=to_you");
  await expect(page.getByRole("link", { name: /Kan I komme onsdag\?|Må jeg tale med en person\?/ })).toBeVisible();
  // «Marker som klaret» hands the chat back and the row leaves «Til dig».
  await page.getByRole("link", { name: /Må jeg tale med en person\?/ }).click();
  await expect(page).toHaveURL(/\/app\/opkald\/[0-9a-f-]{36}/);
  await page.getByRole("button", { name: "Marker som klaret" }).click();
  await expect(page.getByRole("button", { name: "Marker som klaret" })).toBeDisabled();
  await page.goto("/app/opkald?f=to_you");
  await expect(page.getByText("Ingen opkald eller beskeder passer til filteret.")).toBeVisible();
});

test("16 · Afregning: abonnementet (2.495 kr. + moms) og den godkendte henvendelse uden pris vises tydeligt som forhåndsvisning", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } });
  const lead = await (await page.request.post(`/api/backend/workspaces/${wsId}/leads`, { headers: CSRF, data: { contact_name: "Birgitte Bruun" } })).json();
  await page.request.patch(`/api/backend/workspaces/${wsId}/leads/${lead.id}`, { headers: CSRF, data: { expected_version: lead.version, qualification_status: "qualified" } });
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/leads/${lead.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/konto");
  await expect(page.getByText("Kortbetaling er ikke sat op endnu.", { exact: false })).toBeVisible(); // no Stripe keys in E2E
  await expect(page.getByText("Faktureres, når måneden er slut og kortbetaling er sat op.", { exact: false })).toBeVisible();
  await expect(page.getByText(/i alt 3\.118,75 kr\./)).toBeVisible(); // 2.495 kr. + 25 % moms
  await expect(page.getByText("4,00 kr.").first()).toBeVisible(); // 4 kr. pr. udgående opkald
  await shot(page, info, "afregning");
});

test("Tastatur og fokus: spring-til-indhold, synlig fokusmarkering og navigation uden mus", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  await page.goto("/app/setup");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Spring til indhold" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);
  // Every focusable element reached by Tab shows a visible focus indicator.
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    await page.waitForTimeout(250); // transition-all animates outline-width in
    const style = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const cs = getComputedStyle(el);
      return { tag: el.tagName, outline: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2, shadow: cs.boxShadow !== "none" };
    });
    if (style) expect(style.outline || style.shadow, `fokus synlig på ${style.tag}`).toBeTruthy();
  }
  await shot(page, info, "fokus");
  await page.goto("/app/viden");
  await page.getByRole("link", { name: "Ugen", exact: true }).first().focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/ugen/);
});

test("17 · Viden: forslag fra hjemmesiden bliver til kladder med tekst og uden gættede priser", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  servers.push(await serve(4000, `<!doctype html><html lang="da"><head><title>Fjord Gulv</title></head><body>
    <h1>Fjord Gulv</h1><p>Vi sliber og behandler trægulve i hele Østjylland.</p>
    <h2>Gulvafslibning</h2><p>Afslibning med støvfrit anlæg. Fra 145 kr. pr. m² inkl. moms.</p>
    <h2>Lakering</h2><p>Tre lag slidstærk lak.</p></body></html>`));
  await page.goto("/app/viden");
  await page.getByRole("button", { name: "Hent fra hjemmesiden" }).click();
  await page.getByLabel("Hjemmesidens adresse").fill("http://127.0.0.1:4000/");
  await page.getByRole("button", { name: "Hent forslag" }).click();
  await expect(page.getByText(/3 forslag lagt som kladder/)).toBeVisible({ timeout: 20_000 });
  await page.goto("/app/viden");
  await expect(page.getByText(/Dialogbot foreslår · Ydelse/).first()).toBeVisible();
  await expect(page.getByText(/Hjemmesiden nævner prisen/).first()).toBeVisible();
  await shot(page, info, "viden-forslag-fra-hjemmeside");
  // Nothing is live before approval; a wrong suggestion is rejected.
  let live = await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json();
  expect(live.items).toEqual([]);
  page.once("dialog", (d) => d.accept("Passer ikke"));
  const lak = page.locator("div").filter({ hasText: "Lakering" }).filter({ has: page.getByRole("button", { name: "Afvis" }) }).last();
  await lak.getByRole("button", { name: "Afvis" }).click();
  await expect(page.getByText("Lakering")).toHaveCount(0);
  live = await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json();
  expect(live.items).toEqual([]);
});

test("18 · Trin 1: hjemmesiden udfylder beskrivelse, CVR, telefon og adresse; åbningstider kommer som kladde og godkendes med ét klik", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  servers.push(await serve(4000, `<!doctype html><html lang="da"><head><title>Fjord Gulv</title></head><body>
    <h1>Fjord Gulv</h1><p>Vi sliber og behandler trægulve i hele Østjylland.</p>
    <h2>Gulvafslibning</h2><p>Afslibning med støvfrit anlæg.</p>
    <footer>Fjord Gulv ApS · Havnevej 12 · 8000 Aarhus · CVR 12345674 · Ring på 70 12 34 56 hverdage 8-16</footer></body></html>`));
  await page.goto("/opsaetning/1");
  await page.getByLabel("Hjemmesidens adresse").fill("http://127.0.0.1:4000/");
  await page.getByRole("button", { name: /^Hent/ }).click();
  await expect(page.getByText(/Fundet på/)).toBeVisible({ timeout: 25_000 });
  await expect(page.getByText(/CVR: 12345674/)).toBeVisible();
  await expect(page.getByLabel(/^Hvad I laver/)).toHaveValue(/\S/);
  await expect(page.getByLabel("Åbningstider")).toHaveValue(/08.*16/);
  await shot(page, info, "trin1-fra-hjemmeside");
  // Nothing from the site is live until approved; «Godkend alle» approves what was found.
  let live = await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json();
  expect(live.items).toEqual([]);
  await page.getByRole("button", { name: /^Godkend alle/ }).click();
  await expect(page.getByText(/Alt er godkendt/)).toBeVisible();
  live = await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json();
  expect(live.items.length).toBeGreaterThan(0);
  await page.getByText("CVR og adresse (valgfrit)").click();
  await expect(page.getByLabel("CVR")).toHaveValue("12345674");
  await expect(page.getByLabel("Adresse", { exact: true })).toHaveValue("Havnevej 12");
});

test("19 · Reception: manuskriptet foreslås af AI, rettes og gemmes; kanalerne vises", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/indstillinger/hilsen");
  await expect(page.getByRole("heading", { name: "Jeres digitale reception" })).toBeVisible();
  await expect(page.getByText(/Forslag fra AI er sat ind/)).toBeVisible();
  await expect(page.getByLabel(/Det skal assistenten spørge om/)).toHaveValue(/navn/);
  await page.getByLabel("Navn på assistenten (valgfri)").fill("Sofie");
  await page.getByRole("button", { name: "Gem manuskript" }).click();
  await expect(page.getByText(/Gemt\. Assistenten bruger manuskriptet/)).toBeVisible();
  await expect(page.getByText("Aktiv version 1")).toBeVisible();
  await shot(page, info, "r05-reception");
});

test("20 · I dag og beskeder: en ny henvendelse vises under «Til dig» og som besked; hjælpen findes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  await page.request.post(`/api/backend/workspaces/${wsId}/leads`, { headers: CSRF, data: { contact_name: "Mette", contact_phone: "+4520304050", need_summary: "Tilbud på afslibning" } });
  await page.goto("/app");
  await expect(page.getByRole("link", { name: /1 nye henvendelser/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Åbn: Ny henvendelse: Mette/ })).toBeVisible();
  await shot(page, info, "overblik");
  await page.goto("/app/notifications");                 // retired: notifications are «Til dig» on I dag and in Opkald
  await expect(page).toHaveURL(/\/app\/opkald\?f=to_you/);
  await page.goto("/app/hjaelp");
  await expect(page.getByRole("heading", { name: "Sådan bruger I Dialogbot" })).toBeVisible();
});

test("21 · Bookinger: tider følger godkendte åbningstider; en manuel booking bliver til aftale, henvendelse og kalenderfeed", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const week = [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], open: "08:00", close: "16:00" }];
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "opening_hours", title: "Åbningstider", content: { weekly: week } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/aftaler");
  await expect(page.getByRole("heading", { name: "Aftaler, Dialogbot har booket" })).toBeVisible();
  await expect(page.getByText(/Der er ingen bookingtyper endnu/)).toBeVisible();
  // Types and rules live in Alle indstillinger → Booking (a sheet).
  await page.goto("/app/indstillinger?ark=booking");
  await expect(page.getByRole("dialog", { name: "Booking" })).toBeVisible();
  await page.getByLabel("Navn", { exact: true }).fill("Besigtigelse");
  await page.getByRole("button", { name: "Tilføj type" }).click();
  await expect(page.getByText("Besigtigelse", { exact: true })).toBeVisible();
  await page.getByLabel("Kunder må booke i chatten og i telefonen").check();
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByText("Gemt.")).toBeVisible();
  await expect(page.getByLabel("Kalenderabonnement")).toHaveValue(/\/api\/v1\/public\/calendar\/[\w-]+\.ics$/);
  await page.goto("/app/aftaler");
  await expect(page.getByText("Slået til", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Hvornår").locator("option").first()).toHaveText(/Først ledige – .*kl\. (0[89]|1[0-5])\.\d\d$/);
  await page.getByLabel("Navn", { exact: true }).fill("Mette Jensen");
  await page.getByLabel("Telefon", { exact: true }).fill("+4520304050");
  await page.getByRole("button", { name: "Book", exact: true }).click();
  await expect(page.getByText(/^Booket .+ kl\. .+\.$/)).toBeVisible();
  // The week with the appointment: the card opens, and the lead made from it is one click away.
  const list = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings?days=14`)).json();
  const day = new Date(list.items[0].starts_at).toLocaleDateString("sv-SE", { timeZone: "Europe/Copenhagen" });
  await page.goto(`/app/aftaler?uge=${day}`);
  await page.getByRole("button", { name: /Mette Jensen/ }).click();
  await shot(page, info, "aftaler-uge");
  await page.getByRole("link", { name: "Henvendelse" }).first().click();
  await expect(page.getByText(/Booket besigtigelse/)).toBeVisible();
});

test("22 · Kampagner: manuskript foreslås af AI, kontakter importeres med lovkrav, og start er ærlig om manglende opsætning", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/kampagner");
  await expect(page.getByRole("heading", { name: "Vil I også ringe ud?" })).toBeVisible();
  await page.getByRole("button", { name: "Ja, slå udgående opkald til" }).click();
  await expect(page.getByRole("heading", { name: "Ring til jeres kunder – én kampagne ad gangen" })).toBeVisible();
  await expect(page.getByText(/4,00 kr\. \+ moms pr\. udgående opkald/)).toBeVisible();
  await page.getByLabel("Navn på kampagnen").fill("Forårstilbud");
  await page.getByLabel("Hvad skal opkaldet handle om?").fill("Tilbyde gulvafslibning til tidligere kunder");
  await page.getByRole("button", { name: "Opret kampagne" }).click();
  await expect(page.getByRole("heading", { name: "Forårstilbud" })).toBeVisible();
  await expect(page.getByText(/Forslag fra AI er sat ind/)).toBeVisible();
  await expect(page.getByLabel(/^Første replik/)).toHaveValue(/digitale assistent/);
  await page.getByRole("button", { name: "Gem kampagne" }).click();
  await expect(page.getByText("Gemt.")).toBeVisible();
  // the assistant is an automated caller: every contact needs documented consent – businesses too (§ 10)
  await page.getByLabel("Eller indsæt listen").fill("Navn;Telefon;Firma\nMette Hansen;20 30 40 50;Hansen Byg ApS\nForkert;123;X");
  await page.getByLabel("Virksomheder", { exact: true }).check();
  await expect(page.getByRole("button", { name: "Tilføj kontakter" })).toBeDisabled();
  await page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?").fill("Bad om opkald på messen, marts 2026");
  await page.getByRole("button", { name: "Tilføj kontakter" }).click();
  await expect(page.getByText(/1 kontakter tilføjet, 1 ugyldige numre \(fx række 2\)/)).toBeVisible();
  await expect(page.getByText("+4520304050")).toBeVisible();
  await expect(page.getByText(/Højst 8,00 kr\. \+ moms/)).toBeVisible();
  // the start is explicit and honest: outbound calling is not set up by Dialogbot in this environment
  await expect(page.getByText(/Udgående opkald er ikke sat op hos Dialogbot endnu/)).toBeVisible();
  const start = page.getByRole("button", { name: "Start kampagne" });
  await expect(start).toBeDisabled();
  for (const box of await page.getByRole("group", { name: "Bekræft reglerne for opkald" }).getByRole("checkbox").all()) await box.check();
  await expect(start).toBeDisabled(); // stays disabled while outbound calling is not configured
  await expect(page.getByText("Kladde", { exact: true })).toBeVisible();
  await shot(page, info, "c02-kampagne");
  await page.goto("/app/kampagner");
  await page.getByLabel("Telefonnummer").fill("21 22 23 24");
  await page.getByRole("button", { name: "Spær nummer" }).click();
  await expect(page.getByText("+4521222324")).toBeVisible();
});

function wavBytes(seconds = 6, rate = 24000): Buffer {
  const n = rate * seconds, data = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) data.writeInt16LE(Math.round(3000 * Math.sin((2 * Math.PI * 220 * i) / rate)), i * 2);
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + data.length, 4); h.write("WAVE", 8); h.write("fmt ", 12); h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32);
  h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

test("23 · Stemmer: operatør udgiver en kontrolleret stemme; ejer lytter, vælger, gemmer udtale; valget følger ny session og testsamtale (simuleret motor)", async ({ page, browser }, info) => {
  const { wsId, email } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const post = async (path: string, data: unknown = {}) => {
    const r = await page.request.post(`/api/backend${path}`, { headers: CSRF, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  await post("/dev/operator/self");
  const rights: string[] = [];
  for (const [kind, subject] of [["code", `chatterbox ${info.project.name}`], ["model", `weights ${info.project.name}`], ["dataset", `coral-tts ${info.project.name}`]]) {
    const r = await post("/operator/voice-rights", { kind, subject, license: "E2E" });
    await post(`/operator/voice-rights/${r.id}/review`, { status: "verified", notes: "E2E: gennemgået i testmiljø" });
    rights.push(r.id);
  }
  const slug = `e2e-${info.project.name.replace(/\W/g, "")}-${Date.now()}`.toLowerCase();
  const profile = await post("/operator/voices", { slug, display_name: "E2E Testrøst", visibility: "workspace", workspace_id: wsId });
  const ref = await (await page.request.post(`/api/backend/operator/voices/${profile.id}/references?source_id=e2e`, { headers: { ...CSRF, "content-type": "audio/wav" }, data: wavBytes() })).json();
  const withVersion = await post(`/operator/voices/${profile.id}/versions`, { model_repo: "ResembleAI/chatterbox", model_revision: "e".repeat(40), references: [ref], rights_record_ids: rights });
  const vid = withVersion.versions[0].id;
  await post(`/operator/voice-versions/${vid}/checks/run`);
  await post(`/operator/voice-versions/${vid}/submit`);
  await post(`/operator/voice-versions/${vid}/approve`);
  await post(`/operator/voice-versions/${vid}/activate`);

  await page.goto("/app/indstillinger/stemmer");
  await expect(page.getByRole("heading", { name: "Dansk stemme til jeres assistent" })).toBeVisible();
  await expect(page.getByText(/talemotoren er simuleret/)).toBeVisible();
  // ready-made Danish voices with portraits: Camilla is used until another is chosen
  await expect(page.getByRole("heading", { name: "Vælg telefonstemme" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Camilla" }).getByText("Bruges nu")).toBeVisible();
  await page.getByRole("button", { name: "Vælg Peter" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Peter" }).getByText("Bruges nu")).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E Testrøst" })).toBeVisible();
  await expect(page.getByText("Pilot i jeres arbejdsrum")).toBeVisible();
  await page.getByRole("button", { name: "Afspil prøve med E2E Testrøst" }).click();
  await expect(page.getByText("Afspiller simuleret lyd (testmotor).")).toBeVisible();
  await page.getByRole("button", { name: "Vælg som standard" }).click();
  await expect(page.getByText("Standard", { exact: true })).toBeVisible();
  await page.getByLabel(/^Tekst \(højst/).fill("Det koster 2.495 kroner om måneden.");
  await page.getByRole("button", { name: "Generér og afspil" }).click();
  await expect(page.getByText("Afspiller simuleret lyd (testmotor).")).toBeVisible();
  await page.getByLabel("Ord 1").fill("ApS");
  await page.getByLabel("Udtale 1").fill("a p s");
  await page.getByRole("button", { name: "Gem udtaleordbog" }).click();
  await expect(page.getByText(/Version 2\./)).toBeVisible();
  await shot(page, info, "v01-stemmer");
  // a new browser session sees the same saved choice
  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL });
  const p2 = await ctx.newPage();
  await login(p2, email);
  await p2.goto("/app/indstillinger/stemmer");
  await expect(p2.getByText("Standard", { exact: true })).toBeVisible();
  await ctx.close();
  // test call (simulated telephony + simulated engine): the call's assistant uses the chosen voice, pinned per call
  await post(`/operator/telephony/workspaces/${wsId}/numbers`, { e164: `+4570${String(Date.now()).slice(-6)}`, provider_number_id: `pn_${slug}`, activate: true, note: "E2E: nummer tilknyttet af operatør" });
  const item = await post(`/workspaces/${wsId}/knowledge/items`, { kind: "service", title: "Gulvafslibning", content: { description: "Vi sliber gulve." } });
  await post(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`);
  await post(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`);
  const vapi = await page.request.post(`${process.env.API_BASE_URL ?? "http://localhost:8000"}/api/v1/webhooks/vapi`, {
    headers: { authorization: "Bearer e2e-only-vapi-secret-0123456789" },
    data: { message: { type: "assistant-request", call: { id: `call_${slug}`, phoneNumberId: `pn_${slug}` } } } });
  const assistant = (await vapi.json()).assistant;
  expect(assistant.voice.provider).toBe("custom-voice");
  const speech = await page.request.post(assistant.voice.server.url.replace(/^https?:\/\/[^/]+/, process.env.API_BASE_URL ?? "http://localhost:8000"), {
    headers: { "x-vapi-secret": "e2e-only-vapi-secret-0123456789" },
    data: { message: { type: "voice-request", text: "Din tid er den 28. oktober kl. 10.30.", sampleRate: 16000 } } });
  expect(speech.status()).toBe(200);
  expect(speech.headers()["x-simulated"]).toBe("1");
  expect((await speech.body()).length).toBeGreaterThan(1000);
});

test("24 · Egen stemme: samtykke i eget navn, personligt manuskript, optagelse sætning for sætning, indsendelse til gennemgang og tilbagetrækning", async ({ page }, info) => {
  test.setTimeout(180_000);
  await freshOwner(page, info);
  await page.goto("/app/indstillinger/stemmer");
  await page.getByRole("link", { name: "Indtal jeres egen stemme" }).click();
  await expect(page.getByRole("heading", { name: "Indtal jeres egen stemme" })).toBeVisible();
  await expect(page.getByText(/Ligheden med indtaleren kan variere/)).toBeVisible();
  await page.getByLabel("Indtalerens fulde navn").fill("Mette Hansen");
  await page.getByLabel("By eller område").fill("Aarhus");
  await expect(page.getByText(/Jeg, Mette Hansen, er den person/)).toBeVisible();
  await page.getByLabel("Indtaleren skriver sit fulde navn").fill("Mette Hansen");
  await page.getByLabel("Jeg er indtaleren og giver samtykke som beskrevet ovenfor.").check();
  await page.getByRole("button", { name: "Start indtaling" }).click();
  await expect(page.getByRole("heading", { name: "Indtaling: Mette Hansen" })).toBeVisible();
  await expect(page.getByText("0 af 15 godkendt")).toBeVisible();
  for (let i = 0; i < 15; i++) {
    const item = page.locator("ol > li").nth(i);
    await item.getByRole("button", { name: "Optag", exact: true }).click();
    await page.waitForTimeout(1600);
    await item.getByRole("button", { name: "Stop og gem" }).click();
    await expect(item.getByText(/^(Godkendt|Ikke godkendt)$/)).toBeVisible();
    if (await item.getByText("Ikke godkendt", { exact: true }).isVisible()) {
      throw new Error(`sætning ${i + 1} blev ikke godkendt: ${await item.innerText()}`);
    }
  }
  await expect(page.getByText("15 af 15 godkendt")).toBeVisible();
  await shot(page, info, "v02-egen-stemme");
  await page.getByRole("button", { name: "Send til gennemgang" }).click();
  await expect(page.getByText("Afventer Dialogbots gennemgang af samtykket og en prøve af stemmen.")).toBeVisible();
  await page.getByRole("button", { name: "Træk samtykket tilbage" }).click();
  await page.getByRole("button", { name: "Træk samtykket tilbage" }).last().click();
  await expect(page.getByText(/Samtykket er trukket tilbage\. Optagelserne er slettet/)).toBeVisible();
});

test("25 · Integrationer: ærligt katalog, Zapier med signeret webhook, Google Kalender via OAuth (simuleret) og afbryd", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/indstillinger/integrationer");
  await expect(page.getByRole("heading", { name: "Handlinger i jeres egne systemer" })).toBeVisible();
  await expect(page.getByText(/Testmiljø: forbindelser og handlinger er simulerede/)).toBeVisible();
  for (const h of ["Klar", "Via Zapier eller Make", "På vej"]) await expect(page.getByRole("heading", { name: h, exact: true })).toBeVisible();
  // Dialogbots own calendar is honest: not connected until online booking is on
  const own = page.locator('[data-connector="bookings"]');
  await expect(own.getByText("Ikke forbundet")).toBeVisible();
  // Zapier: paste the Catch Hook address, get the signing secret exactly once, test the connection
  const zap = page.locator('[data-connector="zapier"]');
  await zap.getByLabel(/Catch Hook/).fill("http://localhost:9/hook");
  await zap.getByRole("button", { name: "Forbind" }).click();
  await expect(zap.getByText("Vises kun én gang", { exact: false })).toBeVisible();
  await expect(zap.getByText(/^whsec_/)).toBeVisible();
  await expect(zap.getByText("Forbundet (simuleret)")).toBeVisible();
  await zap.getByRole("button", { name: "Test forbindelse" }).click();
  await expect(zap.getByText("Forbindelsen virker (simuleret).")).toBeVisible();
  // Google Calendar: OAuth round-trip through the (simulated) provider and back
  const g = page.locator('[data-connector="google_calendar"]');
  await g.getByRole("button", { name: "Forbind" }).click();
  await expect(page.getByText("Google Kalender er forbundet.")).toBeVisible();
  await expect(page.locator('[data-connector="google_calendar"]').getByText("Forbundet (simuleret)")).toBeVisible();
  await shot(page, info, "c03-integrationer");
  // disconnect Zapier with an in-page confirmation
  const zap2 = page.locator('[data-connector="zapier"]');
  await zap2.getByRole("button", { name: "Afbryd" }).click();
  await zap2.getByRole("button", { name: "Ja, afbryd Zapier" }).click();
  await expect(page.locator('[data-connector="zapier"]').getByText("Ikke forbundet")).toBeVisible();
  await expect(page.getByText("Seneste handlinger")).toBeVisible();
});

test("26 · Ambassadør: ung tilmelder sig via regelquiz, forælder godkender, operatør godkender, kunde kommer via link og får rabat", async ({ page, browser }, info) => {
  const CSRF = { "x-requested-with": "dialogbot" };
  const tag = `${info.project.name}-${Date.now()}`;
  const parentEmail = `e2e-parent-${tag}@example.com`;
  // 1. The programme page is public; sign-up works past the preview gate when it leads to /ambassador.
  await page.goto("/ambassador/bliv");
  await expect(page.getByRole("heading", { name: /Anbefal Dialogbot/ })).toBeVisible();
  await shot(page, info, "amb-program");
  await page.getByRole("link", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/signup\?next=%2Fambassador%2Fbliv|\/signup\?next=\/ambassador\/bliv/);
  const email = uniqueEmail("amb", info);
  await page.getByLabel("Dit navn").fill("Mads Jensen");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/ambassador\/bliv/);
  await expect(page.getByText(/Bekræft din e-mail først/)).toBeVisible();
  const token = (await latestMailLink(page.request, /token=[\w-]+/)).split("=")[1];
  expect((await page.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  await page.reload();

  // 2. Sign-up form: 17 years old → a parent must confirm; one wrong quiz answer is refused and explained.
  const born = new Date(); born.setFullYear(born.getFullYear() - 17); born.setDate(born.getDate() - 20);
  await page.getByLabel("Fødselsdato").fill(born.toISOString().slice(0, 10));
  await expect(page.getByText("Du er under 18 – en forælder skal godkende")).toBeVisible();
  await page.getByLabel("Forælders navn").fill("Lone Jensen");
  await page.getByLabel("Forælders e-mail").fill(parentEmail);
  await page.getByLabel("Din hilsen på din side (valgfri)").fill("Min onkel bruger den i sit VVS-firma");
  await page.getByLabel("Ja, bare det er en firmamail").check();
  await page.getByLabel("At det er reklame, fx #reklame, og at jeg får bonus").check();
  await page.getByLabel("Nej, AI-opkald kræver, at de har sagt ja først").check();
  await page.getByLabel("Nej, dem ringer jeg ikke til med reklame").check();
  await page.getByRole("button", { name: "Tilmeld mig som ambassadør" }).click();
  await expect(page.getByText("Forkert – læs reglerne til venstre og prøv igen.")).toBeVisible();
  await page.getByLabel("Nej, ikke uden at de har sagt ja til det først").check();
  await shot(page, info, "amb-tilmelding");
  await page.getByRole("button", { name: "Tilmeld mig som ambassadør" }).click();
  await expect(page).toHaveURL(/\/ambassador$/);
  await expect(page.getByText("Afventer godkendelse")).toBeVisible();
  await expect(page.getByText(/Vi venter på, at din forælder/)).toBeVisible();

  // 3. An operator approves.
  const opCtx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const op = await opCtx.newPage();
  await freshOwner(op, info);
  expect((await op.request.post("/api/backend/dev/operator/self", { headers: CSRF, data: {} })).ok()).toBeTruthy();
  await op.goto("/app/operator/ambassadors");
  await expect(op.getByRole("heading", { name: "Ambassadører", exact: true })).toBeVisible();
  await op.getByRole("link", { name: "Mads Jensen" }).first().click();
  await expect(op.getByText("ikke godkendt endnu")).toBeVisible();
  await op.getByRole("button", { name: "Godkend" }).click();
  await expect(op.getByText("Aktiv", { exact: true })).toBeVisible();
  await shot(op, info, "amb-operator-detalje");

  // 4. The ambassador now has a link and a code, and ready-made texts marked as advertising.
  await page.reload();
  await expect(page.getByText("Personligt link")).toBeVisible();
  const link = (await page.locator("p.select-all").first().textContent())!.trim();
  expect(link).toMatch(/\/a\/mads-jensen(-\d+)?$/);
  await shot(page, info, "amb-portal");
  await page.getByRole("button", { name: /Del og tekster/ }).click();
  await expect(page.getByText(/#reklame/).first()).toBeVisible();

  // 5. The parent confirms from the e-mail link.
  const parentCtx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const parent = await parentCtx.newPage();
  await parent.request.post("/api/backend/auth/register", { headers: CSRF, data: { email: parentEmail, password: DEMO_PASSWORD, display_name: "Lone Jensen" } });
  await parent.request.post("/api/auth/login", { headers: CSRF, data: { email: parentEmail, password: DEMO_PASSWORD } });
  const consent = await latestMailLink(parent.request, /\/ambassador\/foraelder\?token=[\w-]+/);
  await parent.goto(consent.replace(/^https?:\/\/[^/]+/, ""));
  await expect(parent.getByRole("heading", { name: "Godkend ambassadøraftale" })).toBeVisible();
  await parent.getByLabel(/Jeg er forælder\/værge/).check();
  await shot(parent, info, "amb-foraelder");
  await parent.getByRole("button", { name: "Godkend aftalen" }).click();
  await expect(parent.getByText(/Aftalen er godkendt/)).toBeVisible();

  // 6. A customer follows the link: the front page opens without a preview code and shows the welcome discount.
  const custCtx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const cust = await custCtx.newPage();
  await cust.goto(new URL(link).pathname);
  await expect(cust).toHaveURL(/\/\?anbefalet=mads-jensen(-\d+)?$/);
  await expect(cust.getByText(/Mads har anbefalet Dialogbot til dig/)).toBeVisible();
  await shot(cust, info, "amb-kunde-forside");
  const cEmail = uniqueEmail("ambkunde", info);
  expect((await cust.request.post("/api/backend/auth/register", { headers: CSRF, data: { email: cEmail, password: DEMO_PASSWORD, display_name: "Kunde" } })).status()).toBe(201);
  await cust.request.post("/api/auth/login", { headers: CSRF, data: { email: cEmail, password: DEMO_PASSWORD } });
  const ct = (await latestMailLink(cust.request, /token=[\w-]+/)).split("=")[1];
  await cust.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token: ct } });
  await cust.goto("/opsaetning/1");
  await expect(cust.getByText("Du kom via en ambassadørs link")).toBeVisible();
  await cust.getByLabel("Navn (som den siger det)").fill(`Hansen VVS ${tag}`);
  await cust.getByRole("button", { name: "Videre" }).click();
  await expect(cust.getByLabel("Navn (som den siger det)")).toHaveValue(`Hansen VVS ${tag}`);
  await cust.goto("/app/konto");
  await expect(cust.getByText(/I er anbefalet af Mads/)).toBeVisible();

  // 7. The ambassador sees the customer (company name and status only).
  await page.reload();
  await page.getByRole("button", { name: /Kunder/ }).click();
  await expect(page.getByText(`Hansen VVS ${tag}`)).toBeVisible();
  await expect(page.getByText("i gang med opstart")).toBeVisible();
  await Promise.all([opCtx.close(), parentCtx.close(), custCtx.close()]);
});


test("Skal v2: fire faner, avatar til Konto, bundfaner på telefon, assistent, og alle gamle adresser redirecter", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  await page.goto("/app");
  const mobile = (page.viewportSize()?.width ?? 1440) < 640;
  const tabs = mobile ? page.locator("nav[aria-label='Sider']").last() : page.locator("header nav[aria-label='Sider']");
  for (const label of ["I dag", "Det ved den", "Opkald", "Ugen"]) await expect(tabs.getByRole("link", { name: label })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Mere/ })).toHaveCount(0);
  await expect(tabs.getByRole("link", { name: "I dag" })).toHaveAttribute("aria-current", "page");
  await tabs.getByRole("link", { name: "Opkald" }).click();
  await expect(page).toHaveURL(/\/app\/opkald$/);
  await expect(tabs.getByRole("link", { name: "Opkald" })).toHaveAttribute("aria-current", "page");
  // The assistant: a column on a wide screen, a full-screen sheet behind «Ændr noget» elsewhere.
  if (page.viewportSize()!.width < 1280) {
    await page.getByRole("button", { name: "Ændr noget" }).click();
    await expect(page.getByRole("dialog", { name: "Ændr noget" })).toBeVisible();
    await shot(page, info, "skal-assistent-ark");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  } else {
    await expect(page.getByRole("complementary", { name: "Ændr noget" })).toBeVisible();
  }
  await page.getByRole("link", { name: /^Konto:/ }).click();
  await expect(page).toHaveURL(/\/app\/konto$/);
  await shot(page, info, "skal-konto");
  // No horizontal page scroll at either width.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  const OLD: [string, RegExp][] = [
    ["/app/overview", /\/app$/], ["/app/knowledge?tab=k03", /\/app\/viden\?tab=k03/], ["/app/inbox", /\/app\/opkald$/], ["/app/leads", /\/app\/opkald\?f=to_you$/],
    ["/app/tasks", /\/app\/opkald\?f=to_you$/], ["/app/notifications", /\/app\/opkald\?f=to_you$/], ["/app/reports", /\/app\/ugen$/], ["/app/bookings", /\/app\/aftaler$/],
    ["/app/campaigns", /\/app\/kampagner$/], ["/app/settings/team", /\/app\/konto$/], ["/app/settings/profile", /\/app\/konto$/], ["/app/billing", /\/app\/konto$/],
    ["/app/settings/agreement", /\/app\/konto$/], ["/app/settings/telephony", /\/app\/indstillinger\?ark=telefoni$/], ["/app/settings", /\/app\/indstillinger$/],
    ["/app/reception", /\/app\/indstillinger\?ark=hilsen$/], ["/app/voices", /\/app\/indstillinger\?ark=stemmer$/], ["/app/help", /\/app\/hjaelp$/], ["/app/not-yet", /\/app\/hjaelp$/],
  ];
  for (const [from, to] of OLD) {
    const r = await page.request.get(from, { maxRedirects: 0 });
    expect(r.status(), from).toBe(308);
    await page.goto(from);
    await expect(page, from).toHaveURL(to);
  }
});

test("Opsætning trin 1→3: virksomhed, stemme, nummer, kontrolkode, dokumentation, prøveopkald og «Tænd» – og så lander man på I dag", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const post = async (path: string, data: unknown = {}) => {
    const r = await page.request.post(`/api/backend${path}`, { headers: CSRF, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  const item = await post(`/workspaces/${wsId}/knowledge/items`, { kind: "service", title: "Gulvafslibning", content: { price_net_minor: 14500 } });
  await post(`/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`);
  await post(`/workspaces/${wsId}/agreement`, { model: "A" });
  const own = `+4520${String(Date.now()).slice(-6)}`;

  // Trin 1
  await page.goto("/opsaetning/1");
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill(own);
  await page.getByLabel(/^Hvad I laver/).fill("Gulvafslibning og lakering");
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /Videre til trin 3/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/3/);
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toBeDisabled();

  // Trin 3 A · stemme
  await page.getByRole("radio", { name: "Vælg" }).last().click();
  await expect(page.getByRole("radio", { name: "Valgt" })).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`/api/backend/workspaces/${wsId}/voices`)).json()).settings.standard_voice).toBeTruthy();

  // Trin 3 B · nummer → kontrolkode → dokumentation → forbind
  const text = await page.locator("main").innerText();
  for (const word of ["Vapi", "Twilio", "webhook", "Server URL", "Bearer", "API-nøgle", "nummer-id"]) expect(text).not.toContain(word);
  await expect(page.getByLabel("Dit nummer – det, kunderne ringer til")).toHaveValue(own);
  await page.getByLabel("Hvad slags abonnement er det?").selectOption("mobile");
  await page.getByRole("button", { name: "Gem nummer" }).click();
  await page.getByRole("button", { name: "Ring mig op med en kode" }).click();
  await expect(page.getByText(/Opkaldet er på vej/)).toBeVisible();
  const code = (await (await page.request.get(`/api/backend/dev/telephony/verification-code?workspace_id=${wsId}`, { headers: CSRF })).json()).code;
  await page.getByLabel("Koden").fill(code);
  await page.getByRole("button", { name: "Bekræft", exact: true }).click();
  await page.getByLabel("CVR-nummer").fill("12345678");
  await page.getByLabel("Adresse i Danmark").fill("Østergade 1, 8000 Aarhus C");
  await page.locator("input[type=file]").setInputFiles({ name: "cvr.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 cvr-udskrift") });
  await page.getByRole("button", { name: "Send dokumentation" }).click();
  await page.getByRole("button", { name: "Forbind telefonen" }).click();
  await expect(page.getByText(/gennemgår jeres virksomhedsdokumentation/).first()).toBeVisible();
  // Dialogbot's operator reviews the documentation; the job buys and connects the number (simulated provider).
  await post("/dev/operator/self");
  await post(`/operator/telephony/workspaces/${wsId}/documents/review`, { status: "approved", note: "CVR-udskrift kontrolleret i E2E", regulatory_bundle_sid: "BU" + "e".repeat(32) });
  await post(`/operator/telephony/workspaces/${wsId}/jobs/run`);
  await page.reload();
  const dest = (await (await page.request.get(`/api/backend/workspaces/${wsId}/telephony`)).json()).destination.e164 as string;
  await expect(page.getByText(`**61*${dest}#`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toBeDisabled();
  await expect(page.getByText(/Mangler: gennemfør prøveopkaldet/)).toBeVisible();
  await shot(page, info, "trin3-guide");

  // Prøveopkald (the provider's webhooks are posted the way the provider would)
  await page.getByRole("button", { name: "Start prøveopkald" }).click();
  await expect(page.getByText(/ring nu fra en anden telefon/)).toBeVisible();
  const api = process.env.API_BASE_URL ?? "http://localhost:8000";
  const auth = { authorization: `Bearer ${process.env.VAPI_SERVER_SECRET ?? "e2e-only-vapi-secret-0123456789"}` };
  const callId = `call_s3_${info.project.name}_${Date.now()}`;
  const req = await page.request.post(`${api}/api/v1/webhooks/vapi`, { headers: auth, data: { message: { type: "assistant-request", call: { id: callId, customer: { number: "+4540404040" } }, phoneNumber: { number: dest } } } });
  expect((await req.json()).assistant.firstMessage).toContain("Dette er et prøveopkald");
  const report = await page.request.post(`${api}/api/v1/webhooks/vapi`, { headers: auth, data: { message: {
    type: "end-of-call-report", endedReason: "customer-ended-call", analysis: { summary: "Prøveopkald." }, phoneNumber: { number: dest },
    call: { id: callId, customer: { number: "+4520304050" }, startedAt: new Date(Date.now() - 65_000).toISOString(), endedAt: new Date().toISOString() },
    artifact: { messages: [{ role: "bot", message: "Dette er et prøveopkald." }, { role: "user", message: "Hej." }] } } } });
  expect((await report.json()).outcome).toBe("applied");
  await page.reload();
  await expect(page.getByText(/Prøveopkaldet lykkedes \(simuleret\)/)).toBeVisible();
  await expect(page.getByText("Alt er klar – tænd Dialogbot")).toBeVisible();
  await shot(page, info, "trin3-klar");
  await page.getByRole("button", { name: "Tænd Dialogbot" }).click();
  await expect(page).toHaveURL(/\/app\?taendt=1/);
  await expect(page.getByText("Dialogbot er tændt").first()).toBeVisible();
  await shot(page, info, "trin3-tændt");
  // Done: /app no longer sends this workspace back to the setup.
  await page.context().clearCookies({ name: "db_setup_later" });
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});

test("Opsætning trin 2: kalender forbindes (simuleret), eller springes over – og tid tages kun, hvis «Booke aftaler» er valgt", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/2");
  await expect(page).toHaveURL(/\/opsaetning\/3/); // booking was not chosen: trin 2 is skipped
  await page.goto("/opsaetning/1");
  await page.getByRole("checkbox", { name: /Booke aftaler/ }).check();
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await page.goto("/opsaetning/2");
  await expect(page.getByRole("heading", { name: "Hvor skal aftalerne lande?" })).toBeVisible();
  await expect(page.getByText("0×")).toBeVisible();
  await shot(page, info, "trin2");
  await page.getByRole("button", { name: "Forbind" }).first().click();
  await expect(page).toHaveURL(/\/opsaetning\/2\?connected=google_calendar/, { timeout: 15_000 });
  await expect(page.getByText(/er forbundet/).first()).toBeVisible();
  await page.getByRole("button", { name: /Videre til trin 3/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/3/);
  // Defaults: one 45-minute type, switched on.
  const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/settings`)).json();
  expect(s.enabled).toBe(true);
  expect(s.types[0].duration_minutes).toBe(45);
  // Skipping turns «Booke aftaler» off again.
  await page.goto("/opsaetning/2");
  await page.getByRole("button", { name: /Spring over/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/3/);
  const g = await (await page.request.get(`/api/backend/workspaces/${wsId}/goals`)).json();
  expect(g.booking).toBe(false);
});


test("Ændr noget: åbningstider med egne ord → før → efter → Godkend; intet gælder før; «Nej» ændrer intet; test som kunde", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app");
  const narrow = (page.viewportSize()?.width ?? 1440) < 1280;
  if (narrow) await page.getByRole("button", { name: "Ændr noget" }).click();
  const ask = page.getByLabel("Skriv, hvad du vil ændre").filter({ visible: true });
  const live = async () => JSON.stringify((await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json()).items);

  await ask.fill("Ret åbningstider: åbningstider man-fre 8-16");
  await ask.press("Enter");
  const card = page.getByRole("group", { name: /Ændring: Åbningstider/ }).filter({ visible: true });
  await expect(card.getByText("Ikke angivet", { exact: true })).toBeVisible();
  await expect(card.getByText("Man–fre 08–16", { exact: true })).toBeVisible();
  await shot(page, info, "assistent-foer-efter");
  expect(await live()).not.toContain("08:00");                                   // nothing gælder før «Godkend»
  await card.getByRole("button", { name: "Godkend" }).click();
  await expect(card.getByText(/Godkendt og gemt/)).toBeVisible();
  expect(await live()).toContain("08:00");

  // «Nej, lad være» changes nothing.
  await ask.fill("åbningstider man-fre 9-17");
  await ask.press("Enter");
  const second = page.getByRole("group", { name: /Ændring: Åbningstider/ }).filter({ visible: true }).last();
  await expect(second.getByText("Man–fre 09–17", { exact: true })).toBeVisible();
  await second.getByRole("button", { name: "Nej, lad være" }).click();
  await expect(second.getByText("Intet ændret.")).toBeVisible();
  expect(await live()).toContain("08:00");
  expect(await live()).not.toContain("09:00");

  // Not understood → a link, never an error.
  await ask.fill("bla bla");
  await ask.press("Enter");
  await expect(page.getByRole("link", { name: "Alle indstillinger" }).filter({ visible: true }).first()).toBeVisible();

  // The second state: ask as a customer (answers only from approved knowledge).
  if (narrow) await page.keyboard.press("Escape");
  await page.goto("/app/viden");
  if (narrow) await page.getByRole("button", { name: "Ændr noget" }).click();
  await page.getByRole("button", { name: "Test mig som kunde" }).filter({ visible: true }).click();
  await page.getByLabel("Skriv et spørgsmål, som en kunde ville stille").filter({ visible: true }).fill("Hvornår har I åbent?");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/\[fake\] svar på/).filter({ visible: true }).first()).toBeVisible();
  await shot(page, info, "assistent-test-som-kunde");
});

test("Opsætningen har assistenten «Jeg hjælper med trin N»", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  await page.getByRole("button", { name: "Hjælp" }).click();
  await expect(page.getByRole("dialog", { name: "Jeg hjælper med trin 1" })).toBeVisible();
  await page.getByRole("button", { name: "Hvad sker der i trin 2?" }).click();
  await expect(page.getByText(/forbinder du din kalender/)).toBeVisible();
});
