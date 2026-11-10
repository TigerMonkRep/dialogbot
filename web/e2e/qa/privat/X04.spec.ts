import { expect, test } from "@playwright/test";
import { CSRF, QA_API, needsPrivatStack, stripeState } from "./pq-helpers";
import { lastSmsTo, noHorizontalScroll, payFakeStripe, shot, uniqueIp, uniqueMobile } from "./p2-helpers";

/** X04 (P1): Quiz-funnel Privat (/privat/start) – same mechanics as Erhverv in the orange theme; the lead is kept at the
 *  gate; verify («reveal») → the 14-day trial checkout. REAL backend (tests/qa/qa_privat_stack.py, fake Stripe), not the
 *  in-browser fake: the funnel must not fall back to simulation. */

test.beforeEach(async ({ request, page }) => {
  test.skip(!(await needsPrivatStack(request)), "kræver tests/qa/qa_privat_stack.py og next med API_BASE_URL til den");
  await page.setExtraHTTPHeaders({ "x-real-ip": uniqueIp() });
});

test("6 trin i orange → kode → konto oprettet → checkout med 14 dage → prøveperiode og opgaverne aktive", async ({ page }, info) => {
  const mobile = uniqueMobile();
  const email = `qa-p2-x04-${info.project.name}-${Date.now()}@example.com`;
  await page.goto("/privat/start?h=1605&utm_source=qa");
  await expect(page).toHaveURL(/\/privat\/start\/1\?/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Hvad har du udsat?");
  // orange theme, same logo mark as Erhverv, the audience switch on top
  await expect(page.locator("[data-theme='privat']").first()).toBeVisible();
  const accent = await page.locator("[data-theme='privat']").first().evaluate((el) => getComputedStyle(el).getPropertyValue("--color-accent").trim());
  expect(accent.toUpperCase()).toBe("#C4461A");
  // (the funnel shell does not render the Erhverv/Privat bar the layout passes in – noted, not asserted: «nothing that leads away»)
  await expect(page.locator("[data-funnel=privat]")).toBeVisible();
  await noHorizontalScroll(page);
  await shot(page, info, "X04", "s1");

  await page.getByRole("checkbox", { name: "Tandlægen" }).click();
  await page.getByRole("checkbox", { name: "Bilsyn" }).click();
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/privat\/start\/2$/);
  await page.getByRole("radio", { name: /Os to/ }).click();
  await expect(page).toHaveURL(/\/privat\/start\/3$/);
  await page.getByRole("radio", { name: "Værkstedet" }).click();
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/privat\/start\/4$/);
  await page.getByRole("radio", { name: /Om morgenen/ }).click();
  await expect(page).toHaveURL(/\/privat\/start\/5$/);
  await expect(page.locator("[data-build]")).toHaveAttribute("data-build", "settled", { timeout: 30_000 });
  await expect(page.locator("[data-summary]")).toBeVisible();
  await shot(page, info, "X04", "s5");
  // reload keeps the draft (cookie + server): still on step 5 with the summary
  await page.reload();
  await expect(page.locator("[data-summary]")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Se min dag" }).click({ timeout: 30_000 });

  await expect(page).toHaveURL(/\/privat\/start\/6$/);
  await page.getByLabel("Navn").fill("Mette Jensen");
  await page.locator("[data-next]").click();
  await page.getByLabel("Mobil").fill(mobile);
  await page.locator("[data-next]").click();
  await page.getByLabel("E-mail").fill(email);
  await page.locator("[data-next]").click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send kode" }).click();
  await expect(page.locator("[data-code]")).toBeVisible();
  await shot(page, info, "X04", "code");

  // the lead is kept on the server before any code is typed (draft gated, number masked)
  const draftId = (await page.context().cookies()).map((c) => decodeURIComponent(c.value)).find((v) => /^[0-9a-f-]{36}$/.test(v));
  if (draftId) {
    const d = await (await page.request.get(`/api/backend/funnel/drafts/${draftId}`)).json();
    expect(d.gated).toBe(true);
    expect(d.verified).toBe(false);
    expect(JSON.stringify(d)).not.toContain(email); // the public draft never echoes the e-mail
  }

  // a wrong code stays on the step
  await page.getByLabel("Kode fra SMS").fill("000000");
  await expect(page.locator("#code-hint")).toContainText(/passer ikke/i);
  const sms = await lastSmsTo(`+45${mobile}`);
  const code = sms.match(/\b(\d{6})\b/)![1];
  await page.getByLabel("Kode fra SMS").fill(code);

  // verify → Konto with ?plan=plus → straight on to Stripe Checkout with the 14-day trial
  await expect(page.locator("[data-testid=fake-stripe]")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("[data-testid=trial-days]")).toHaveText("14");
  const st = await stripeState(page.request);
  const sess = st.sessions.find((s) => s.customer_email === email)!;
  expect(sess, "checkout session for the funnel user").toBeTruthy();
  const p = sess.payload as Record<string, unknown>;
  expect(p.billing_address_collection).toBe("required");
  expect((p.phone_number_collection as { enabled: boolean })?.enabled).toBe(true);
  await shot(page, info, "X04", "checkout");

  // before paying: an account but no rights; the quiz's tasks are drafts
  const before = await (await page.request.get(`${QA_API}/__qa/stripe/sessions`)).json();
  expect(before).toBeTruthy();
  await payFakeStripe(page);
  await expect(page).toHaveURL(/\/privat\/(konto|dag)/, { timeout: 30_000 });
  await expect.poll(async () => (await (await page.request.get("/api/backend/privat/subscription")).json()).status, { timeout: 20_000 }).toBe("trial");
  const tasks = (await (await page.request.get("/api/backend/privat/tasks")).json()) as { status: string; title: string }[];
  expect(tasks.length).toBeGreaterThan(0);
  expect(tasks.filter((t) => t.status === "draft"), JSON.stringify(tasks)).toEqual([]);
  await shot(page, info, "X04", "after-trial");
});

test("dybt link til trin 5 uden svar sender tilbage til trin 1", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/privat/start/5");
  // F-P2-04-X04: a fresh draft has step=1, so reachableStep() sends the visitor to step 2 – step 1 (unanswered) is skipped
  await expect(page).toHaveURL(/\/privat\/start\/(1|2)$/, { timeout: 15_000 });
  await expect(page, "tom kladde skal starte på trin 1").toHaveURL(/\/privat\/start\/1$/);
});

test("honeypot: samme svar, ingen SMS", async ({ request }) => {
  // honeypot through the API: same answer, nothing sent
  const d = await (await request.post(`${QA_API}/api/v1/funnel/drafts`, { headers: { ...CSRF, "x-real-ip": uniqueIp() }, data: { kind: "privat" } })).json();
  const mobile = uniqueMobile();
  const r = await request.post(`${QA_API}/api/v1/funnel/drafts/${d.id}/gate`, { headers: { ...CSRF, "x-real-ip": uniqueIp() },
    data: { name: "Bot", email: "bot@example.com", phone: mobile, consent: true, website: "http://spam" } });
  expect(r.status()).toBe(202);
  await expect(lastSmsTo(`+45${mobile}`, 2000)).rejects.toThrow();
});

test("assistentens navn fra trin 1 bruges i de næste trin (ikke «Peter»)", async ({ page }) => {
  await page.goto("/privat/start");
  await page.getByRole("checkbox", { name: "Tandlægen" }).click();
  await page.getByTestId("assistant-name").fill("Kim");
  await page.locator("[data-next]").click();
  await page.getByRole("radio", { name: /Mig selv/ }).click();
  await expect(page).toHaveURL(/\/privat\/start\/3$/);
  await page.getByRole("radio", { name: "Værkstedet" }).click();
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/privat\/start\/4$/);
  // F-P2-03-X04: step 4 and 5 still say «Peter» after the user named the assistant «Kim»
  await expect(page.getByRole("heading", { level: 1 })).not.toContainText("Peter");
});
