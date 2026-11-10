import { expect, test, type Page } from "@playwright/test";
import { CSRF, evidence, needsPrivatStack, privatUser, QA_API, stripeState, subscription, waitIdle } from "./pq-helpers";

/** X07 (P0): «Prøv gratis i 14 dage» → checkout (navn, adresse, telefon, e-mail, kort) → adgang først efter gennemført
 *  Stripe-setup; 3DS, afvist kort. Real Privat backend + fake Stripe hosted page (tests/qa/qa_privat_stack.py). */

test.beforeEach(async ({ request }) => {
  test.skip(!(await needsPrivatStack(request)), "kræver tests/qa/qa_privat_stack.py på :8100 og next på BASE_URL med API_BASE_URL=:8100");
});

const plusTrial = (page: Page) => page.getByTestId("plan-plus").getByRole("button", { name: "Start 14 dage gratis" });

async function toCheckout(page: Page) {
  await page.goto("/privat/konto");
  await waitIdle(page);
  await plusTrial(page).click();
  await expect(page.getByTestId("fake-stripe")).toBeVisible({ timeout: 20_000 });
  expect(page.url()).toContain(`${QA_API}/__qa/stripe/pay/cs_test_qa_`);
  return page.url().split("/pay/")[1];
}

async function fill(page: Page, card: string, email?: string) {
  await page.getByLabel("Navn på kortholder").fill("Mette Hansen");
  await page.getByLabel("Adresse").fill("Abildgade 18");
  await page.getByLabel("Postnummer").fill("8200");
  await page.getByLabel("By").fill("Aarhus N");
  await page.getByLabel("Telefon").fill("+4520304050");
  if (email !== undefined) await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Kortnummer").fill(card);
  await page.getByRole("button", { name: /Start 14 dages prøveperiode/ }).click();
}

async function noAccess(page: Page) {
  const s = await subscription(page);
  expect([s.status, s.plan, s.entitled, s.calls_quota]).toEqual(["none", "none", false, 0]);
  const me = await (await page.request.get("/api/backend/privat/me")).json();
  expect(me.entitled).toBe(false);
  // An app that needs the plan cannot be switched on, and an own list stays a draft.
  const app = await page.request.post("/api/backend/privat/addons/kalender/enable", { headers: CSRF });
  expect(app.status(), await app.text()).toBeGreaterThanOrEqual(400);
}

test("forsidens «Prøv gratis i 14 dage» fører en logget-ind bruger uden plan direkte til checkout", async ({ page }, info) => {
  await privatUser(page, info, "x07-cta");
  await page.goto("/privat");
  await page.getByRole("link", { name: "Prøv gratis i 14 dage" }).first().click();
  await page.waitForLoadState("networkidle");
  await evidence(page, info, "X07", "cta-landing");
  // Krav X07 / agentdefinition: «"Prøv gratis i 14 dage" leads straight to checkout (name, address, phone, e-mail, card)».
  await expect(page.getByTestId("fake-stripe"), `landede på ${page.url()}`).toBeVisible({ timeout: 10_000 });
});

test("anonym besøgende: «Prøv gratis i 14 dage» fører til oprettelse (ikke til en demo med «Prøveperiode · Plus»)", async ({ page }, info) => {
  await page.goto("/privat");
  await page.getByRole("link", { name: "Prøv gratis i 14 dage" }).first().click();
  await page.waitForLoadState("networkidle");
  await evidence(page, info, "X07", "cta-anonymous");
  await expect(page, `landede på ${page.url()}`).toHaveURL(/\/(signup|login)|__qa\/stripe\/pay\//);
});

test("trial-checkout: afbrudt, afvist, ingen dækning, 3DS afvist → ingen adgang; 3DS godkendt → 14 dages Plus", async ({ page }, info) => {
  const { email } = await privatUser(page, info, "x07-flow");
  await page.goto("/privat/konto");
  await waitIdle(page);
  await expect(page.getByTestId("balance-chip").filter({ visible: true }).first()).toHaveAttribute("data-status", "none");
  await expect(page.getByTestId("subscription-card").filter({ visible: true })).toContainText("Ingen plan");
  await noAccess(page);

  // 1. The checkout asks for name, address, phone, e-mail (prefilled) and card – and offers exactly 14 trial days.
  const sid1 = await toCheckout(page);
  for (const label of ["Navn på kortholder", "Adresse", "Postnummer", "By", "Telefon", "E-mail", "Kortnummer"])
    await expect(page.getByLabel(label)).toBeVisible();
  await expect(page.getByLabel("E-mail")).toHaveValue(email);
  await expect(page.getByTestId("trial-days")).toHaveText("14");
  const sess = (await stripeState(page.request)).sessions.find((s) => s.id === sid1)!;
  expect(sess.payload).toMatchObject({ mode: "subscription", payment_method_collection: "always", billing_address_collection: "required",
    phone_number_collection: { enabled: true }, subscription_data: { trial_period_days: 14 } });
  await evidence(page, info, "X07", "checkout-fields");

  // 2. Abandoned: «Tilbage» → cancel_url; no access.
  await page.getByRole("link", { name: "Tilbage" }).click();
  await expect(page).toHaveURL(/\/privat\/konto/);
  await waitIdle(page);
  await expect(page.getByTestId("account-note").filter({ visible: true })).toHaveText("Du afbrød valget af plan. Der er ikke trukket noget.");
  await noAccess(page);

  // 3. Declined, insufficient funds, 3DS failed: error on the Stripe page, the session stays open, no access.
  const sid2 = await toCheckout(page);
  await fill(page, "4000 0000 0000 0002");
  await expect(page.getByTestId("stripe-error")).toHaveText("Dit kort blev afvist.");
  await fill(page, "4000 0000 0000 9995");
  await expect(page.getByTestId("stripe-error")).toHaveText("Dit kort har ikke dækning nok.");
  await fill(page, "4000 0025 0000 3155");
  await expect(page.getByTestId("fake-3ds")).toBeVisible();
  await page.getByRole("link", { name: "Afvis" }).click();
  await expect(page.getByTestId("stripe-error")).toContainText("Godkendelsen af betalingen mislykkedes");
  await evidence(page, info, "X07", "declined");
  expect((await stripeState(page.request)).sessions.find((s) => s.id === sid2)!.status).toBe("open");
  await page.goto("/privat/konto");
  await waitIdle(page);
  await noAccess(page);
  await expect(page.getByTestId("balance-chip").filter({ visible: true }).first()).toHaveAttribute("data-status", "none");

  // 4. Reload / back from a session that never completed: still nothing.
  const s = await (await page.request.get(`/api/backend/privat/subscription?session_id=${sid2}`)).json();
  expect([s.status, s.entitled]).toEqual(["none", false]);

  // 5. 3DS approved → back on Konto, the trial runs with Plus rights for 14 days.
  await toCheckout(page);
  await fill(page, "4000 0025 0000 3155");
  await page.getByRole("link", { name: "Godkend" }).click();
  await expect(page).toHaveURL(/\/privat\/konto/, { timeout: 20_000 });
  await waitIdle(page);
  await expect(page.getByTestId("account-note").filter({ visible: true })).toHaveText("Dit abonnement er aktivt.");
  await expect(page.getByTestId("balance-chip").filter({ visible: true }).first()).toHaveAttribute("data-status", "trial");
  const after = await subscription(page);
  expect([after.status, after.plan, after.entitled, after.trial_days_left, after.calls_quota]).toEqual(["trial", "plus", true, 14, 10]);
  await evidence(page, info, "X07", "trial-active");
  await page.reload();
  await waitIdle(page);
  await expect(page.getByTestId("balance-chip").filter({ visible: true }).first()).toHaveAttribute("data-status", "trial");

  // 6. One trial per account: a new checkout carries no second trial.
  const again = await (await page.request.post("/api/backend/privat/subscription/checkout", { headers: CSRF, data: { plan: "plus", interval: "month" } })).json();
  const sid3 = String(again.url).split("/pay/")[1];
  const p3 = (await stripeState(page.request)).sessions.find((x) => x.id === sid3)!.payload as { subscription_data: Record<string, unknown> };
  expect(p3.subscription_data.trial_period_days).toBeUndefined();
});

test("tilbage fra checkout uden gennemført betaling: Konto må ikke sige «Dit abonnement er aktivt»", async ({ page }, info) => {
  await privatUser(page, info, "x07-lie");
  const sid = await toCheckout(page);
  await fill(page, "4000 0000 0000 0002");  // declined: the session stays open
  // The user (or a shared/bookmarked link) lands on the success URL anyway.
  await page.goto(`/privat/konto?abonnement=ok&session_id=${sid}`);
  await waitIdle(page);
  await page.waitForTimeout(1500);
  await evidence(page, info, "X07", "success-url-without-payment");
  const s = await subscription(page);
  expect([s.status, s.entitled]).toEqual(["none", false]);  // the backend holds
  await expect(page.getByTestId("balance-chip").filter({ visible: true }).first()).toHaveAttribute("data-status", "none");
  await expect(page.getByText("Dit abonnement er aktivt.").filter({ visible: true })).toHaveCount(0);  // … and the page must not claim otherwise
});
