import { expect, test, type Page } from "@playwright/test";
import { DEMO_PASSWORD, PREVIEW_CODE, latestMailLink, shot, uniqueEmail } from "../helpers";

/* S0 «Erhverv døgnåbent» (Fürster 11/11): a business can sign up and choose its plan day and night, without being rung
 * first, and the chat links to the sign-up. The browser clock is set to 21:30 Copenhagen time – after the calling hours
 * (SALES_CALL_FROM/SALES_CALL_TO, 08–20) – and nothing may close, hide or say «lukket».
 * Flow: /erhverv → «Opret dig» → /signup → verify mail link → opsætning trin 1 → Konto: bekræft abonnement → card
 * checkout (Stripe Checkout faked in the browser when Stripe is configured; CI has no Stripe keys, so the honest
 * «ikke sat op» note is checked instead – as journey 16 does). */
const NIGHT = new Date("2026-11-11T21:30:00+01:00");
const SIGNUP = /\/signup\?intent=reception$/;
const NEXT_OPEN = "2026-11-12T07:00:00+00:00"; // Thursday 08:00 in Copenhagen
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
  await expect(page).toHaveURL(/\/opsaetning\/1/);
  await page.getByLabel("Navn (som den siger det)").fill("S0 Nat ApS");
  await page.getByRole("button", { name: "Videre" }).click();
  await expect(page.getByRole("checkbox", { name: /Tage telefonen/ })).toBeChecked(); // the intent from sign-up
  await shot(page, info, "s0-opsaetning");

  // Plan: the owner confirms the subscription on Konto (no call, no person needed), then the card.
  await page.context().addCookies([{ name: "db_setup_later", value: "1", url: page.url() }]);
  await page.goto("/app/konto#abonnement");
  await page.getByRole("button", { name: "Bekræft abonnement" }).click();
  await expect(page.getByText(/Bekræftet · aftale v1/)).toBeVisible();
  const addCard = page.getByRole("button", { name: "Tilføj betalingskort" });
  if (await addCard.isVisible().catch(() => false)) {
    // Stripe configured (test keys): Stripe Checkout is faked – it returns straight to Konto as Stripe would.
    await page.route("**/billing/card/checkout", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ url: "/app/konto?card=saved" }) }));
    await addCard.click();
    await expect(page).toHaveURL(/card=saved/);
    await expect(page.getByText("Tak – kortet er gemt hos Stripe.", { exact: false })).toBeVisible();
  } else {
    await expect(page.getByText("Kortbetaling er ikke sat op endnu.", { exact: false })).toBeVisible();
  }
  await shot(page, info, "s0-abonnement");
});

test("S0 · chatten efter kl. 20: svarer med link til oprettelsen, og et ønsket opkald sættes i kø – ingen blindgyde", async ({ page }, info) => {
  await page.clock.install({ time: NIGHT });
  // The sales line as production has it after 20:00: available, closed now, next opening 08:00 (GET /demo-call).
  await page.route("**/api/backend/demo-call", (r) => r.request().method() === "GET"
    ? r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      available: true, demo_number: "+4593703433", open_now: false, next_open: NEXT_OPEN, signup_url: "/signup?intent=reception",
      hours: { from: "08:00", to: "20:00" }, consent_version: "demo-call-web-later-v1",
      consent_text: "Ja tak, Peter fra Dialogbot, en digital assistent, må ringe mig op på dette nummer, når Dialogbot åbner for opkald igen (fra kl. 08:00), og vise, hvordan Dialogbot tager telefonen.",
      agent: "Peter", voices: [], industries: [] }) })
    : r.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ status: "scheduled", scheduled_for: NEXT_OPEN }) }));
  let asked: { messages: { content: string }[] } | null = null;
  await page.route("**/api/backend/demo-call/chat", async (r) => {
    asked = r.request().postDataJSON();
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      reply: "Abonnementet koster det samme hele døgnet. Du kan oprette dig selv med det samme – også nu i aften.", refused: false,
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

  // «Ja, ring til mig» after 20:00: honest about when, and the sign-up right there – never «kom tilbage».
  await page.getByRole("button", { name: "Ja, ring til mig" }).click();
  await expect(log.getByText(/jeg ringer i morgen fra kl\. 08:00\. Du behøver ikke vente: du kan oprette dig med det samme/)).toBeVisible();
  await expect(log.locator("[data-signup-link]").last()).toBeVisible();
  await page.locator("#chat-input").fill("S0 Byg ApS");
  await page.getByRole("button", { name: /^Send/ }).click();
  await page.getByRole("button", { name: "Håndværker" }).click();
  await page.locator("#chat-input").fill("20 30 40 50");
  await expect(page.getByText(/når Dialogbot åbner for opkald igen \(fra kl\. 08:00\)/)).toBeVisible(); // the consent says when
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: /Ring mig op/ }).click();
  await expect(log.getByText(/Jeg ringer til 20 30 40 50 i morgen fra kl\. 08:00 og præsenterer mig som receptionist for S0 Byg ApS/)).toBeVisible();
  await expect(page.getByText("Peter ringer i morgen fra kl. 08:00")).toBeVisible();
  await expect(page.getByText(CLOSED_WORDS)).toHaveCount(0);
  await shot(page, info, "s0-chat-efter-20");
  await log.locator("[data-signup-link]").last().click();
  await expect(page).toHaveURL(/\/signup\?intent=reception/);
  await expect(page.getByLabel("Jeg vil starte med")).toHaveValue("reception");
});

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
