import { expect, test } from "@playwright/test";
import { DEMO_PASSWORD, PREVIEW_CODE, SEEDED, freshOwner, latestMailLink, login, shot, uniqueEmail } from "./helpers";

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
  // Colleagues invited by e-mail must reach signup without a preview code.
  await page.goto("/signup?next=/invite/abc");
  await expect(page).toHaveURL(/\/signup\?next=/);
  await expect(page.getByRole("button", { name: "Opret konto" })).toBeVisible();
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
