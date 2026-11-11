import { expect, test, type Page } from "@playwright/test";
import { DEMO_PASSWORD, SEEDED, skipSetupGate } from "../../helpers";
import { CSRF, evid, snap } from "./p1a-helpers";

/* QA A02 (e2e-erhverv A, wave 2): /login – login, remembered destination, validation and invalid-credential state.
 * Source: web/src/app/login/page.tsx, web/src/proxy.ts (next=), web/src/lib/safe-next.ts, web/src/lib/client.ts:14
 * (expired session → /login?expired=1&next=…), app/modules/identity/service.py:login. */
const ID = "A02";
evid(ID);

async function fill(page: Page, email: string, password: string) {
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill(password);
}

for (const who of ["owner", "staff", "reader"] as const) {
  test(`A02 · ${who} logger ind og lander i appen; sessionen overlever genindlæsning`, async ({ page }, info) => {
    await skipSetupGate(page);
    await page.goto("/login");
    await fill(page, SEEDED[who], DEMO_PASSWORD);
    await page.getByRole("button", { name: "Log ind" }).click();
    await expect(page).toHaveURL(/\/app/);
    const me = await (await page.request.get("/api/backend/auth/me")).json();
    expect(me.email).toBe(SEEDED[who]);
    await page.reload();
    await expect(page).toHaveURL(/\/app/);
    // A logged-in visitor who opens /login is sent on, not shown the form again.
    await page.goto("/login");
    await expect(page).toHaveURL(/\/app/);
    if (who === "owner") await snap(page, info, ID, "logget-ind");
  });
}

test("A02 · husket destination: dybt link med query → login → samme side med samme query", async ({ page }) => {
  await skipSetupGate(page);
  await page.goto("/app/indstillinger?ark=telefoni");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Findstillinger%3Fark%3Dtelefoni/);
  await fill(page, SEEDED.owner, DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/app\/indstillinger\?ark=telefoni$/);
});

test("A02 · forkert adgangskode: klar fejl, ingen session, felterne bevares; ukendt e-mail giver samme svar", async ({ page }, info) => {
  await page.goto("/login");
  await fill(page, SEEDED.owner, "Forkert-Kode-2026");
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page.getByText("Forkert e-mail eller adgangskode")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByLabel("E-mail")).toHaveValue(SEEDED.owner);
  expect((await page.request.get("/api/backend/auth/me")).status()).toBe(401);
  await snap(page, info, ID, "forkert-kode");
  const a = await page.request.post("/api/auth/login", { headers: CSRF, data: { email: SEEDED.owner, password: "x-wrong-x-wrong" } });
  const b = await page.request.post("/api/auth/login", { headers: CSRF, data: { email: "findes-ikke-e2a@example.com", password: "x-wrong-x-wrong" } });
  expect(a.status()).toBe(401); expect(b.status()).toBe(401);
  expect((await a.json()).code).toBe((await b.json()).code); // no account enumeration
});

test("A02 · validering: tomme felter og ugyldig e-mail sendes ikke", async ({ page }) => {
  let posts = 0;
  page.on("request", (r) => { if (r.url().includes("/api/auth/login") && r.method() === "POST") posts++; });
  await page.goto("/login");
  await page.getByRole("button", { name: "Log ind" }).click();
  await fill(page, "ikke-en-email", DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(await page.getByLabel("E-mail").evaluate((e: HTMLInputElement) => e.validity.valid)).toBe(false);
  expect(posts).toBe(0);
});

test("A02 · åben omdirigering: next til et andet domæne ender i /app", async ({ page }) => {
  await skipSetupGate(page);
  for (const next of ["//evil.example/x", "https://evil.example/x", "/\\evil.example"]) {
    await page.context().clearCookies();
    await skipSetupGate(page);
    await page.goto(`/login?next=${encodeURIComponent(next)}`);
    await fill(page, SEEDED.owner, DEMO_PASSWORD);
    await page.getByRole("button", { name: "Log ind" }).click();
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));
    expect(new URL(page.url()).host, `next=${next}`).toBe("localhost:3200");
  }
});

test("A02 · serverfejl (500) og indlæsning: knappen viser «Logger ind…», fejlen vises, og man kan prøve igen", async ({ page }, info) => {
  await skipSetupGate(page);
  let fail = true;
  await page.route("**/api/auth/login", async (r) => {
    if (!fail) return r.continue();
    await new Promise((res) => setTimeout(res, 800));
    return r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal_error", message: "Der skete en fejl hos os. Prøv igen." }) });
  });
  await page.goto("/login");
  await fill(page, SEEDED.owner, DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page.getByRole("button", { name: "Logger ind…" })).toBeDisabled();
  await expect(page.getByText("Der skete en fejl hos os. Prøv igen.")).toBeVisible();
  await snap(page, info, ID, "serverfejl");
  fail = false;
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/app/);
});

test("A02 · dobbeltklik på «Log ind» giver én session og ingen fejl", async ({ page }) => {
  await skipSetupGate(page);
  let posts = 0;
  page.on("request", (r) => { if (r.url().includes("/api/auth/login") && r.method() === "POST") posts++; });
  await page.goto("/login");
  await fill(page, SEEDED.staff, DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).dblclick();
  await expect(page).toHaveURL(/\/app/);
  expect(posts).toBe(1);
});

test("A02 · udløbet session: besked «Din session er udløbet», og efter login tilbage til samme side med query", async ({ page, browser }, info) => {
  await skipSetupGate(page);
  await page.goto("/login");
  await fill(page, SEEDED.reader, DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/app/);
  await page.goto("/app/opkald?f=to_you");
  await page.waitForLoadState("networkidle");
  // Revoke the session server-side from another browser holding the same cookie (as a logout elsewhere / expiry does).
  const cookies = await page.context().cookies();
  const other = await browser.newContext();
  await other.addCookies(cookies);
  expect((await other.request.post("http://localhost:3200/api/auth/logout", { headers: CSRF })).ok()).toBeTruthy();
  await other.close();
  // The browser still holds the (now dead) cookie; the next page load must lead to /login, not a crash (F-E2A-04).
  await page.reload();
  await page.waitForTimeout(3000);
  await snap(page, info, ID, "udloebet");
  await expect(page.getByText("This page couldn’t load")).toHaveCount(0);
  await page.waitForURL(/\/login/, { timeout: 10_000 });
  await expect(page.getByText("Din session er udløbet. Log ind igen for at fortsætte.")).toBeVisible();
  await fill(page, SEEDED.reader, DEMO_PASSWORD);
  await page.getByRole("button", { name: "Log ind" }).click();
  await expect(page).toHaveURL(/\/app\/opkald\?f=to_you$/);
});
