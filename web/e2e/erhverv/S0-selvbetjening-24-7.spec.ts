import { expect, test, type Page } from "@playwright/test";
import { DEMO_PASSWORD, PREVIEW_CODE, latestMailLink, shot, uniqueEmail } from "../helpers";

/* S0 «Erhverv døgnåbent» (Fürster 11/11): a business can sign up and choose its plan day and night, without being rung
 * first, and the chat links to the sign-up. The browser clock is set to 21:30 Copenhagen time and nothing may close,
 * hide or say «lukket». Since 12/11 Peter also rings at once at any hour (no calling hours at all).
 * Flow: /erhverv → «Opret dig» → /signup → verify mail link → opsætning (Virksomhed) → the guide's last step Betaling:
 * bekræft abonnement → card
 * checkout (Stripe Checkout faked in the browser when Stripe is configured; CI has no Stripe keys, so the honest
 * «ikke sat op» note is checked instead – as journey 16 does). */
const NIGHT = new Date("2026-11-11T21:30:00+01:00");
const SIGNUP = /\/signup\?intent=reception$/;
const CLOSED_WORDS = /Kom tilbage der|Prøv igen i det tidsrum|Vi ringer mellem kl\./;

/** Through the P00 preview gate when it is on (CI); with PREVIEW_GATE off /preview just redirects to "/". */
async function unlock(page: Page) {
  await page.goto("/preview");
  const code = page.getByLabel("Invitationskode");
  if (await code.isVisible().catch(() => false)) {
    await code.fill(PREVIEW_CODE);
    await page.getByRole("button", { name: "Lås op og se forsiden" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/preview"));
  }
}

test("S0 · efter kl. 20: /erhverv → Opret dig → signup → bekræft mail → opsætning → abonnement og betaling", async ({ page }, info) => {
  await page.clock.install({ time: NIGHT });
  await unlock(page);
  await page.goto("/da/erhverv");
  expect(await page.evaluate(() => new Date().getHours())).toBeGreaterThanOrEqual(20); // the page lives after 20:00
  // Every way in leads to the self-service sign-up; the call is the second choice, never the only one.
  await expect(page.locator("[data-header-signup]")).toHaveAttribute("href", SIGNUP);
  const hero = page.locator("[data-signup-cta]");
  await expect(hero).toHaveText(/Opret dig – kom i gang nu/);
  await expect(hero).toHaveAttribute("href", SIGNUP);
  await expect(page.getByText("Åbent døgnet rundt – opret dig og vælg abonnement selv.", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: /Prøv den – den ringer til dig/ }).first()).toHaveAttribute("href", "/da/proev");
  await expect(page.getByRole("link", { name: /Opret dig og vælg abonnement/ })).toHaveAttribute("href", SIGNUP);
  await expect(page.getByRole("link", { name: /Opret dig selv/ })).toHaveAttribute("href", SIGNUP);
  await expect(page.getByText(CLOSED_WORDS)).toHaveCount(0);
  await shot(page, info, "s0-erhverv-efter-20");

  await hero.click();
  await expect(page).toHaveURL(/\/signup\?intent=reception/);
  const email = uniqueEmail("s0-night", info);
  await page.getByLabel("Dit navn").fill("S0 Natteugle");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await expect(page.getByLabel("Jeg vil starte med")).toHaveValue("reception");
  await shot(page, info, "s0-signup");
  await page.getByRole("button", { name: "Opret konto" }).click();
  await expect(page).toHaveURL(/\/verify-email/);

  const link = await latestMailLink(page.request, /\/verify-email\?token=[\w-]+/);
  await page.goto(link);
  await expect(page.getByText("Din e-mail er bekræftet.")).toBeVisible();
  await page.getByRole("link", { name: /Fortsæt til arbejdsrum/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/virksomhed/);
  await page.getByLabel("Navn (som den siger det)").fill("S0 Nat ApS");
  await page.getByRole("button", { name: "Videre" }).click();
  await expect(page.getByRole("checkbox", { name: /Tage telefonen/ })).toBeChecked(); // the intent from sign-up
  await shot(page, info, "s0-opsaetning");

  // Plan: the guide's visible last step, Betaling – the owner confirms the subscription (no call, no person needed),
  // then the card. Reached from the stepper, as at any hour.
  await page.getByRole("navigation", { name: "Opsætning" }).getByRole("link", { name: /Betaling/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/betaling$/);
  await page.getByRole("button", { name: "Bekræft abonnement" }).click();
  await expect(page.getByText(/Bekræftet · aftale v1/)).toBeVisible();
  const addCard = page.getByRole("button", { name: "Tilføj betalingskort" });
  if (await addCard.isVisible().catch(() => false)) {
    // Stripe configured (test keys): Stripe Checkout is faked – it returns straight to the Betaling step as Stripe would.
    await page.route("**/billing/card/checkout", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ url: "/opsaetning/betaling?card=saved" }) }));
    await addCard.click();
    await expect(page).toHaveURL(/card=saved/);
    await expect(page.getByText("Tak – kortet er gemt hos Stripe.", { exact: false })).toBeVisible();
  } else {
    await expect(page.getByText("Kortbetaling er ikke sat op endnu.", { exact: false })).toBeVisible();
  }
  await shot(page, info, "s0-abonnement");
});

/* Fürster 12/11: a call asked for on dialogbot.app is rung at once – day and night, every day. No queue, no «i morgen»,
 * no weekday or 08–20 claim. The sales line is faked as the API answers now (GET /demo-call has no calling hours;
 * POST answers «calling»); nothing is dialled. */
const AT_ONCE = [
  { name: "kl. 21:30", at: "2026-11-11T21:30:00+01:00" },
  { name: "kl. 03:00", at: "2026-11-12T03:00:00+01:00" },
  { name: "søndag", at: "2026-11-15T14:00:00+01:00" },
];
const TOMORROW_WORDS = /i morgen|fra kl\. 08|hverdag|kun på hverdage|uden for ringetiden|ikke lige nu|når Dialogbot åbner/i;

for (const when of AT_ONCE) {
  test(`S0 · chatten ${when.name}: svarer med link til oprettelsen, og Peter ringer straks – ingen kø, intet «i morgen»`, async ({ page }, info) => {
    await page.clock.install({ time: new Date(when.at) });
    let posted: Record<string, unknown> | null = null;
    await page.route("**/api/backend/demo-call", (r) => {
      if (r.request().method() === "GET") return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        available: true, demo_number: "+4593703433", signup_url: "/signup?intent=reception", consent_version: "demo-call-web-v2",
        consent_text: "Ja tak, Peter fra Dialogbot, en digital assistent, må ringe mig op på dette nummer nu og vise, hvordan Dialogbot tager telefonen.",
        agent: "Peter", voices: [], industries: [] }) });
      posted = r.request().postDataJSON();
      return r.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ status: "calling" }) });
    });
    let asked: { messages: { content: string }[] } | null = null;
    await page.route("**/api/backend/demo-call/chat", async (r) => {
      asked = r.request().postDataJSON();
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
        reply: "Abonnementet koster det samme hele døgnet. Du kan oprette dig selv med det samme – også nu.", refused: false,
        signup_url: "/signup?intent=reception" }) });
    });
    await unlock(page);
    await page.goto("/da/proev");
    const log = page.getByRole("log");
    await expect(log.getByText(/Hej! Jeg hedder Peter/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Opret dig", exact: true }).first()).toHaveAttribute("href", SIGNUP);
    await expect(page.locator("[data-signup-line]")).toHaveAttribute("href", SIGNUP);

    // Free text: «hvad koster det / hvordan kommer jeg i gang» → the answer carries a link to the sign-up.
    await page.locator("#chat-input").fill("Hvad koster det, og hvordan kommer jeg i gang?");
    await page.getByRole("button", { name: /^Send/ }).click();
    await expect(log.getByText(/Du kan oprette dig selv med det samme/)).toBeVisible();
    expect(asked!.messages.at(-1)!.content).toContain("hvordan kommer jeg i gang");
    await expect(log.locator("[data-signup-link]").last()).toHaveAttribute("href", SIGNUP);

    // «Ja, ring til mig»: straight on to the call, whatever the hour or the day.
    await page.getByRole("button", { name: "Ja, ring til mig" }).click();
    await expect(log.getByText("Super. Hvad hedder din virksomhed?")).toBeVisible();
    await page.locator("#chat-input").fill("S0 Byg ApS");
    await page.getByRole("button", { name: /^Send/ }).click();
    await page.getByRole("button", { name: "Håndværker" }).click();
    await page.locator("#chat-input").fill("20 30 40 50");
    await expect(page.getByText(/må ringe mig op på dette nummer nu/)).toBeVisible(); // the consent is «nu»
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: /Ring mig op/ }).click();
    await expect(log.getByText(/Jeg ringer til 20 30 40 50 nu – du får et opkald fra Peter fra Dialogbot inden for et minut/)).toBeVisible();
    expect(posted).toMatchObject({ phone: "20 30 40 50", company: "S0 Byg ApS", consent: true, consent_version: "demo-call-web-v2" });
    await expect(page.getByText(TOMORROW_WORDS)).toHaveCount(0);
    await expect(page.getByText(CLOSED_WORDS)).toHaveCount(0);
    await shot(page, info, `s0-chat-straks-${when.name.replace(/\W+/g, "")}`);
  });
}

test("S0 · chatten uden salgslinje (som i CI): også da linker den til oprettelsen", async ({ page }) => {
  await page.route("**/api/backend/demo-call/chat", (r) => r.fulfill({ status: 503, contentType: "application/json",
    body: JSON.stringify({ code: "demo_unavailable", message: "Chatten er ikke klar endnu" }) }));
  await unlock(page);
  await page.goto("/da/proev");
  await page.locator("#chat-input").fill("Jeg vil gerne købe det");
  await page.getByRole("button", { name: /^Send/ }).click();
  await expect(page.getByRole("log").getByText(/Chatten er ikke helt klar endnu/)).toBeVisible();
  await expect(page.getByRole("log").locator("[data-signup-link]").last()).toHaveAttribute("href", SIGNUP);
});
