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
  await expect(page.getByRole("heading", { name: /Du driver forretningen/ })).toBeVisible();
  await expect(page.getByText("Privat preview.", { exact: false })).toBeVisible();
  await shot(page, info, "p01-forside");
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
  await expect(page.getByLabel("Produktintention")).toHaveValue("campaigns");
  await page.getByLabel("Virksomhedens officielle navn").fill("E2E Kampagne ApS");
  await shot(page, info, "a06-opret");
  await page.getByRole("button", { name: "Opret og fortsæt" }).click();
  await expect(page).toHaveURL(/\/onboarding\/business/);
  await expect(page.getByText("E2E Kampagne ApS").filter({ visible: true }).first()).toBeVisible();
});

test("2 · A02: forkert adgangskode afvises, login husker destination, log ud", async ({ page }, info) => {
  await page.goto("/app/knowledge");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fknowledge/);
  await page.getByLabel("E-mail").fill(SEEDED.owner);
  await page.getByLabel("Adgangskode", { exact: true }).fill("forkert-kode-123");
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await shot(page, info, "a02-fejl");
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/app\/knowledge/);
  await page.goto("/app/settings/profile");
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

test("4 · O01→O03→O04: virksomhed gemmes før navigation, mål og sprog", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/onboarding/business");
  await page.getByLabel("Kort virksomhedsbeskrivelse & speciale").fill("Gulvafslibning i Storkøbenhavn");
  await page.getByLabel("By").fill("Hellerup");
  await shot(page, info, "o01-virksomhed");
  await page.getByRole("button", { name: /Gem og fortsæt/ }).click();
  await expect(page).toHaveURL(/\/onboarding\/goals/);
  await page.goto("/onboarding/business");
  await expect(page.getByLabel("By")).toHaveValue("Hellerup");
  await page.goto("/onboarding/goals");
  // Empty goals: the AI proposal is filled in first (not saved); the owner adjusts it and saves.
  await expect(page.getByText(/Forslag fra AI er sat ind/)).toBeVisible();
  await expect(page.getByLabel(/Samtalemål/)).toHaveValue(/\S/);
  await page.getByLabel("Aftalebooking").check();
  await page.getByRole("button", { name: "Gem mål" }).click();
  await expect(page.getByText(/Planen er opdateret/)).toBeVisible();
  await shot(page, info, "o03-maal");
  await page.goto("/onboarding/languages");
  await page.getByRole("checkbox", { name: "Engelsk" }).check();
  await page.getByRole("button", { name: "Gem sprog" }).click();
  await expect(page.getByText("Gemt.")).toBeVisible();
  await shot(page, info, "o04-sprog");
});

test("5 · K03→K05: ny ydelse er kladde, indtil ejeren godkender den", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/knowledge?tab=k03");
  await expect(page.getByText(/^0 godkendt/).filter({ visible: true }).first()).toBeVisible();
  await page.getByLabel("Titel").fill("Standard gulvafslibning");
  await page.getByLabel(/Beskrivelse til assistenten/).fill("Afslibning og 2x lak");
  await page.getByLabel("Basispris (ekskl. moms)").fill("145");
  await page.getByRole("button", { name: "Gem som kladde" }).click();
  await expect(page.getByText(/Ændringer afventer godkendelse/)).toBeVisible();
  await shot(page, info, "k03-kladde");
  await page.goto("/app/knowledge?tab=k05");
  await expect(page.getByText("Foreslået ny version")).toBeVisible();
  await expect(page.getByText("145,- kr").first()).toBeVisible();
  await shot(page, info, "k05-gennemgang");
  await page.getByRole("button", { name: "Godkend ny version" }).click();
  await expect(page.getByText("Ingen ændringer afventer")).toBeVisible();
  await page.goto("/app/knowledge?tab=k03");
  await expect(page.getByText("Aktiv & godkendt")).toBeVisible();
});

test("6 · G01/G05: planen viser én næste handling, tjek kører, ikke-byggede trin er ikke tilgængelige", async ({ page }, info) => {
  await login(page, SEEDED.owner);
  await page.goto("/app/setup");
  await expect(page.getByText(/AI ikke aktiv/i).filter({ visible: true }).first()).toBeVisible();
  const desktop = info.project.name.startsWith("desktop");
  if (desktop) {
    await expect(page.getByText(/Næste handling/).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hjælp mig videre" })).toBeVisible();
    await page.getByRole("button", { name: /Udvid alle/ }).click();
    await expect(page.getByText("Ikke tilgængelig endnu").first()).toBeVisible();
  } else {
    await expect(page.getByText("Anbefalet næste handling")).toBeVisible();
    await expect(page.getByText("Ikke tilgængelig").first()).toBeVisible();
  }
  await shot(page, info, "g01-plan");
  await page.getByRole("button", { name: /Kør alle/ }).first().click();
  await expect(page.getByRole("status").filter({ hasText: /bestået/ }).first()).toBeVisible();
  // No fake capability: persona, support and calendar are never shown as working.
  await expect(page.getByText(/Aktiv AI|AI Live/)).toHaveCount(0);
  await page.goto("/app/not-yet?area=Kampagner");
  await expect(page.getByText("Ikke implementeret endnu")).toBeVisible();
});

test("7 · S02→A05: ejer inviterer, kollega accepterer og lander i arbejdsrummet", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const invitee = uniqueEmail("invitee", info);
  await page.goto("/app/settings/team");
  await page.getByLabel("E-mail").fill(invitee);
  await page.getByLabel("Rolle").selectOption("staff");
  await page.getByRole("button", { name: "Send invitation" }).click();
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
  await expect(p2).toHaveURL(/\/app\/setup/);
  const list = await (await p2.request.get("/api/backend/workspaces")).json();
  expect(list.map((w: { id: string }) => w.id)).toContain(wsId);
  await ctx.close();
});

test("8 · Roller: læser kan ikke redigere, medarbejder kan ikke se aktivitetslog, admin kan", async ({ page }, info) => {
  await login(page, SEEDED.reader);
  await page.goto("/onboarding/business");
  await expect(page.getByText(/Din rolle \(læser\)/)).toBeVisible();
  await expect(page.getByLabel("By")).toBeDisabled();
  await page.goto("/app/knowledge?tab=k03");
  await expect(page.getByRole("button", { name: /Gem som ny kladde/ })).toHaveCount(0);
  await shot(page, info, "roller-laeser");
  await page.context().clearCookies();
  await login(page, SEEDED.staff);
  await page.goto("/app/settings/activity");
  await expect(page.getByText(/kun ses af ejere og administratorer/)).toBeVisible();
  await page.context().clearCookies();
  await login(page, SEEDED.admin);
  await page.goto("/app/settings/activity");
  await expect(page.getByRole("heading", { name: "Aktivitetslog" })).toBeVisible();
  await shot(page, info, "s09-log");
});

test("9 · R06: medarbejder tester assistenten mod godkendt viden; læser kan ikke", async ({ page }, info) => {
  await login(page, SEEDED.staff);
  await page.goto("/app/knowledge?tab=r06");
  await expect(page.getByRole("heading", { name: "Test assistenten" })).toBeVisible();
  await expect(page.getByText(/simuleret model, ikke en rigtig AI/)).toBeVisible();
  await page.getByLabel("Spørgsmål fra en kunde").fill("Hvad koster afslibning?");
  await page.getByRole("button", { name: "Spørg assistenten" }).click();
  const answers = page.getByRole("list", { name: "Testsvar" });
  await expect(answers.getByText("[fake] svar på: Hvad koster afslibning?")).toBeVisible();
  await expect(answers.getByText(/assistant-v1 · viden rev\. \d+/)).toBeVisible();
  await shot(page, info, "r06-test-assistenten");
  await page.getByLabel("Spørgsmål fra en kunde").fill("AFVIS dette");
  await page.getByRole("button", { name: "Spørg assistenten" }).click();
  await expect(answers.getByText("Afvist af modellen")).toBeVisible();
  await page.context().clearCookies();
  await login(page, SEEDED.reader);
  await page.goto("/app/knowledge?tab=r06");
  await expect(page.getByText("Test af assistenten kræver rollen medarbejder eller højere.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Spørg assistenten" })).toHaveCount(0);
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

  await page.goto("/app/settings/webchat");
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

  await page.goto("/app/inbox");
  await page.getByRole("link", { name: /Hvad koster gulvafslibning\?/ }).click();
  await expect(page.getByText("[fake] svar på: Hvad koster gulvafslibning?")).toBeVisible();
  await shot(page, info, "indbakke-samtale");
});

test("12 · Henvendelse: kunde beder om kontakt i webchat, ejer kvalificerer, vælger model B, godkender og løser opgaven", async ({ page, browser }, info) => {
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
  await chat.getByLabel("Navn").fill("Henrik Villumsen");
  await chat.getByLabel("E-mail").fill("henrik@example.com");
  await chat.getByLabel("Telefon").fill("+45 20 30 40 50");
  const windowLabel = await chat.getByLabel("Hvornår må vi ringe?").locator("option").last().textContent();
  await chat.getByLabel("Hvornår må vi ringe?").selectOption({ label: windowLabel ?? "" });
  await chat.locator("form.contact").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("Sæt flueben, så virksomheden må kontakte dig.")).toBeVisible(); // consent is required
  await chat.getByLabel("Virksomheden må kontakte mig", { exact: false }).check();
  await chat.locator("form.contact").getByRole("button", { name: "Send" }).click();
  await expect(chat.getByText("Tak, Henrik Villumsen!", { exact: false })).toBeVisible();
  await shot(site, info, "kontakt-i-webchat");
  await ctx.close();

  await page.goto("/app/leads");
  await page.getByRole("link", { name: /Henrik Villumsen/ }).click();
  await expect(page.getByRole("heading", { name: "Henrik Villumsen" })).toBeVisible();
  await expect(page.getByText(`Ring Henrik Villumsen op – ${windowLabel}`)).toBeVisible();
  await expect(page.getByText(/Ønsker opkald/)).toBeVisible();
  await expect(page.getByText("Der er ingen prisaftale endnu", { exact: false })).toBeVisible();
  await page.getByLabel("Kvalificering").selectOption("qualified");
  await page.getByLabel("Forløb").selectOption("contacted");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByLabel("Kvalificering")).toHaveValue("qualified");

  await page.goto("/app/settings/agreement");
  await page.getByRole("button", { name: "Vælg model B" }).click();
  await expect(page.getByText("Gældende: model B", { exact: false })).toBeVisible();
  await shot(page, info, "prisaftale");

  await page.goBack();
  await page.reload();
  await page.getByRole("button", { name: "Godkend henvendelse" }).click();
  await expect(page.getByText("149,00 kr.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Kvalificering")).toBeDisabled();
  await page.getByRole("checkbox", { name: /Færdig: Ring Henrik Villumsen op/ }).check();
  await expect(page.getByRole("checkbox", { name: /Færdig: Ring Henrik Villumsen op/ })).toBeChecked();
  await shot(page, info, "henvendelse-godkendt");
  await page.getByRole("link", { name: "Se samtalen" }).click();
  await expect(page.getByText("Kan I slibe 65 m² plankegulv?").first()).toBeVisible();
});

test("13 · Rapporter: dagens tal er foreløbige og viser nye henvendelser; e-mailindstilling gemmes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/leads`, { headers: CSRF, data: { contact_name: "Rapport Rasmussen", need_summary: "Vil have tilbud på lak" } })).ok()).toBeTruthy();
  await page.goto("/app/reports");
  await expect(page.getByText("Foreløbig – dagen er ikke slut")).toBeVisible();
  await expect(page.getByRole("link", { name: /Rapport Rasmussen/ })).toBeVisible();
  await expect(page.getByText("Godkendte henvendelser (pris ekskl. moms)")).toBeVisible();
  await page.getByLabel("Kl.").selectOption("6");
  await page.getByRole("button", { name: "Gem" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Gemt" })).toBeVisible();
  await shot(page, info, "rapporter");
  await page.reload();
  await expect(page.getByLabel("Kl.")).toHaveValue("6");
});

test("14 · S03: ejer tilknytter nummer, et opkald rapporteres af Vapi og bliver til samtale, henvendelse og opgave", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind: "service", title: "Gulvafslibning", content: { price_net_minor: 14500 } } })).json();
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
  await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF });
  const number = `+4570${String(Date.now()).slice(-6)}`;
  const vapiId = `pn_${info.project.name}_${Date.now()}`;

  await page.goto("/app/settings/telephony");
  await expect(page.getByText("Stemmeforbindelse konfigureret")).toBeVisible();
  await page.getByLabel("Nummer", { exact: true }).fill(number);
  await page.getByLabel("Vapi nummer-id").fill(vapiId);
  await page.getByLabel("Navn", { exact: true }).fill("Hovednummer");
  await page.getByRole("button", { name: "Tilknyt nummer" }).click();
  await expect(page.getByText(number)).toBeVisible();
  await expect(page.getByText("Ingen stemme valgt")).toBeVisible();
  await page.getByRole("button", { name: "Stemme og talestil" }).click();
  await page.getByLabel("ElevenLabs Voice ID").fill("DaNskStemme12345678");
  await page.getByLabel("Talestil (valgfri)").fill("Lun og jordnær, gerne et par jyske vendinger.");
  await page.getByRole("button", { name: "Hør stemmen" }).click();  // no ELEVENLABS_API_KEY in CI: honest notice, no fake audio
  await expect(page.getByText(/kræver en ElevenLabs-nøgle/)).toBeVisible();
  await page.getByRole("button", { name: "Gem stemme" }).click();
  await expect(page.getByText("Dansk stemme valgt")).toBeVisible();
  await shot(page, info, "s03-telefoni");

  const api = process.env.API_BASE_URL ?? "http://localhost:8000";
  const auth = { authorization: `Bearer ${process.env.VAPI_SERVER_SECRET ?? "e2e-only-vapi-secret-0123456789"}` };
  const req = await page.request.post(`${api}/api/v1/webhooks/vapi`, { headers: auth, data: { message: { type: "assistant-request", call: { id: "x", phoneNumberId: vapiId } } } });
  const assistant = (await req.json()).assistant;
  expect(assistant.model.messages[0].content).toContain("Gulvafslibning");
  expect(assistant.model.messages[0].content).toContain("jyske vendinger");
  expect(assistant.voice).toEqual({ provider: "11labs", voiceId: "DaNskStemme12345678", model: "eleven_multilingual_v2" });
  expect(assistant.transcriber.language).toBe("da");
  const report = await page.request.post(`${api}/api/v1/webhooks/vapi`, { headers: auth, data: { message: {
    type: "end-of-call-report", endedReason: "customer-ended-call", analysis: { summary: "Vil have tilbud på afslibning." },
    call: { id: `call_${vapiId}`, phoneNumberId: vapiId, customer: { number: "+4520304050" }, startedAt: "2026-09-24T08:00:00Z", endedAt: "2026-09-24T08:01:05Z" },
    artifact: { messages: [{ role: "bot", message: "Hej, du har ringet til os." }, { role: "user", message: "Hvad koster afslibning?" }] } } } });
  expect((await report.json()).outcome).toBe("applied");

  await page.reload();
  await expect(page.getByText("Vil have tilbud på afslibning.")).toBeVisible();
  await page.goto("/app/inbox");
  await page.getByRole("link", { name: /Hvad koster afslibning\?/ }).click();
  await expect(page.getByRole("heading", { name: "Telefonopkald" })).toBeVisible();
  await page.getByRole("link", { name: /Henvendelse:/ }).click();
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

  await page.goto("/app/inbox");
  await page.getByRole("link", { name: /Må jeg tale med en person\?/ }).click();
  await page.getByLabel("Svar kunden i chatten").fill("Hej, det er Mads fra Fjord. Hvad drejer det sig om?");
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
  await shot(page, info, "indbakke-overtaget");
  await page.goto("/app/inbox");
  await expect(page.getByText("Venter på svar")).toBeVisible();
});

test("16 · Afregning: godkendt henvendelse under model B vises som 149,00 kr. + moms, tydeligt som forhåndsvisning", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const CSRF = { "x-requested-with": "dialogbot" };
  await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "B" } });
  const lead = await (await page.request.post(`/api/backend/workspaces/${wsId}/leads`, { headers: CSRF, data: { contact_name: "Birgitte Bruun" } })).json();
  await page.request.patch(`/api/backend/workspaces/${wsId}/leads/${lead.id}`, { headers: CSRF, data: { expected_version: lead.version, qualification_status: "qualified" } });
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/leads/${lead.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/billing");
  await expect(page.getByText("Dette er en forhåndsvisning – ikke en faktura.", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: "Godkendt henvendelse: Birgitte Bruun" })).toBeVisible();
  await expect(page.getByText("186,25 kr.")).toBeVisible();
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
  await page.goto("/app/knowledge?tab=k03");
  await page.getByRole("link", { name: /Aktive tilbud|Tilbud/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/tab=k04/);
});

test("17 · Viden: forslag fra hjemmesiden bliver til kladder med tekst og uden gættede priser", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  servers.push(await serve(4000, `<!doctype html><html lang="da"><head><title>Fjord Gulv</title></head><body>
    <h1>Fjord Gulv</h1><p>Vi sliber og behandler trægulve i hele Østjylland.</p>
    <h2>Gulvafslibning</h2><p>Afslibning med støvfrit anlæg. Fra 145 kr. pr. m² inkl. moms.</p>
    <h2>Lakering</h2><p>Tre lag slidstærk lak.</p></body></html>`));
  await page.goto("/app/knowledge?tab=k03");
  await expect(page.getByRole("heading", { name: "Hent forslag fra hjemmesiden" })).toBeVisible();
  await page.getByLabel("Hjemmesidens adresse").fill("http://127.0.0.1:4000/");
  await page.getByRole("button", { name: "Hent forslag" }).click();
  await expect(page.getByText("3 forslag oprettet som kladder")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Ydelse: Gulvafslibning")).toBeVisible();
  await page.goto("/app/knowledge?tab=k03");
  await expect(page.getByText(/Hjemmesiden nævner prisen/).first()).toBeVisible();
  await shot(page, info, "k03-forslag-fra-hjemmeside");
  // Nothing is live before approval.
  const live = await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json();
  expect(live.items).toEqual([]);
});

test("18 · O01: hjemmesiden udfylder beskrivelse, CVR, telefon og adresse; åbningstider bliver en kladde", async ({ page }, info) => {
  await freshOwner(page, info);
  servers.push(await serve(4000, `<!doctype html><html lang="da"><head><title>Fjord Gulv</title></head><body>
    <h1>Fjord Gulv</h1><p>Vi sliber og behandler trægulve i hele Østjylland.</p>
    <h2>Gulvafslibning</h2><p>Afslibning med støvfrit anlæg.</p>
    <footer>Fjord Gulv ApS · Havnevej 12 · 8000 Aarhus · CVR 12345674 · Ring på 70 12 34 56 hverdage 8-16</footer></body></html>`));
  await page.goto("/onboarding/business");
  await page.getByRole("switch").uncheck({ force: true }); // visually hidden input behind a styled toggle
  await page.getByRole("textbox", { name: /^Hjemmeside/ }).fill("http://127.0.0.1:4000/");
  await page.getByRole("button", { name: "Hent oplysninger fra hjemmesiden" }).click();
  await expect(page.getByText(/Udfyldt fra hjemmesiden: beskrivelse, CVR, telefon, adresse, postnummer, by/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("textbox", { name: /^CVR/ })).toHaveValue("12345674");
  await expect(page.getByRole("textbox", { name: /^Adresse/ })).toHaveValue("Havnevej 12");
  await expect(page.getByText("08:00 – 16:00")).toBeVisible();
  await shot(page, info, "o01-fra-hjemmeside");
  await page.getByRole("button", { name: "Gem", exact: true }).click();
  await expect(page.getByText("Gemt.")).toBeVisible();
});
