import { expect, test, type Page } from "@playwright/test";
import { evid, snap, unlock, uniqueIp } from "./p1a-helpers";

/* QA P06 (e2e-erhverv A, wave 2): /demo – clearly simulated chat, callback and campaign demonstrations with a reset and
 * signup path. Implementation: /proev (web/src/app/proev/proev-chat.tsx) – a REAL chat with Peter and a REAL callback
 * (POST /demo-call), honest about when it cannot ring. Nothing is dialled here: GET/POST /demo-call are intercepted.
 * Since F-AUD26-02-P06 the call needs an SMS code first (POST /demo-call/code → /verify → /demo-call with the token);
 * those are intercepted too. The real flow against the API is P06-sms-kode.spec.ts. */
const ID = "P06";
evid(ID);
const INFO = { available: true, demo_number: "+4570123456", // no calling hours: Peter rings at once, day and night
  consent_text: "Ja, Dialogbot må ringe mig op én gang nu.", consent_version: "qa", industries: [] };

async function open(page: Page, info: object | number = INFO) {
  await page.setExtraHTTPHeaders({ "x-real-ip": uniqueIp() });
  await unlock(page);
  await page.route("**/api/backend/demo-call", (r) => {
    if (r.request().method() === "GET") return typeof info === "number"
      ? r.fulfill({ status: info, contentType: "application/json", body: JSON.stringify({ code: "internal_error", message: "boom" }) })
      : r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(info) });
    return r.fallback();
  });
  await page.goto("/da/proev");
}
const log = (page: Page) => page.locator("[role=log]").first();

test("P06 · fuld vej: firma → branche → nummer uden samtykke afvises → med samtykke ringer → nulstil og tilmeld", async ({ page }, info) => {
  await page.clock.install();
  await open(page);
  let posts = 0;
  let body: Record<string, unknown> = {};
  await page.route("**/api/backend/demo-call", (r) => {
    if (r.request().method() !== "POST") return r.fallback();
    posts++; body = r.request().postDataJSON();
    return r.fulfill({ status: 202, contentType: "application/json", body: "{}" });
  });
  let codes = 0;
  await page.route("**/api/backend/demo-call/code", (r) => { codes++; return r.fulfill({ status: 202, contentType: "application/json",
    body: JSON.stringify({ status: "code_sent", verification_id: "v-qa", phone_display: "22 83 55 25", resend_after: 30, expires_in: 600 }) }); });
  await page.route("**/api/backend/demo-call/verify", (r) => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ status: "verified", verification_token: "t-qa" }) }));
  await page.getByRole("button", { name: "Ja, ring til mig" }).click();
  await page.clock.runFor(1000);
  await page.locator("#chat-input").fill("Nørgaard Tømrer");
  await page.locator("#chat-input").press("Enter");
  await page.clock.runFor(1000);
  await page.getByRole("button", { name: /Håndværk/ }).first().click();
  await page.clock.runFor(1000);
  await page.locator("#chat-input").fill("22 83 55 25");
  await page.locator("#chat-input").press("Enter");
  await expect(page.getByText(/Sæt kryds|samtykke/i).first()).toBeVisible();
  expect(posts).toBe(0);
  await page.getByRole("checkbox").check();
  await page.locator("#chat-input").fill("22 83 55 25");
  await page.locator("#chat-input").press("Enter");
  await expect.poll(() => codes).toBe(1);
  await expect(page.locator("[data-code-step]")).toContainText("Vi har sendt en kode til 22 83 55 25");
  expect(posts).toBe(0); // nobody is rung before the code
  await page.locator("#chat-input").fill("123456");
  await page.locator("#chat-input").press("Enter");
  await expect.poll(() => posts).toBe(1);
  expect(body).toMatchObject({ company: "Nørgaard Tømrer", consent: true, consent_version: "qa", verification_token: "t-qa" });
  await snap(page, info, ID, "ringer");
  await page.clock.runFor(47_000);
  const signup = page.getByRole("link", { name: /byg|opret|kom i gang/i }).filter({ has: page.locator("xpath=self::*[@href='/signup']") });
  await expect(page.locator("a[href='/signup']").first()).toBeVisible();
  await snap(page, info, ID, "faerdig");
  await page.getByRole("button", { name: /Prøv igen|forfra/i }).last().click();
  await expect(log(page).locator("p")).toHaveCount(1); // back to the greeting only
  void signup;
});

test("P06 · demo slået fra (GET 500): ærlig besked, ingen påstand om opkald, «prøv igen» og kontaktveje", async ({ page }, info) => {
  await open(page, 500);
  await page.getByRole("button", { name: "Ja, ring til mig" }).click();
  await expect(page.locator("main section a[href^='tel:']").first()).toBeVisible();
  await expect(log(page)).not.toContainText(/Jeg ringer nu|ringer til dig nu/i);
  await snap(page, info, ID, "ikke-aaben");
  await page.getByRole("button", { name: /Prøv igen|forfra/i }).first().click();
  await expect(page.getByRole("button", { name: "Ja, ring til mig" })).toBeVisible();
});

test("P06 · serverfejl ved opkaldet (POST 500): personen bliver på nummer-trinnet med fejl", async ({ page }) => {
  await page.clock.install();
  await open(page);
  await page.route("**/api/backend/demo-call/code", (r) => r.request().method() === "POST"
    ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal_error", message: "Der skete en fejl hos os." }) })
    : r.fallback());
  await page.getByRole("button", { name: "Ja, ring til mig" }).click();
  await page.clock.runFor(1000);
  await page.locator("#chat-input").fill("QA Salon"); await page.locator("#chat-input").press("Enter");
  await page.clock.runFor(1000);
  await page.getByRole("button", { name: /Skønhed|Salon|Frisør/i }).first().click();
  await page.clock.runFor(1000);
  await page.getByRole("checkbox").check();
  await page.locator("#chat-input").fill("22 83 55 26"); await page.locator("#chat-input").press("Enter");
  await page.clock.runFor(1500);
  await expect(log(page)).toContainText("Der skete en fejl hos os.");
  await expect(page.getByRole("checkbox")).toBeVisible(); // still on the number step
});

test("P06 · kampagne-demonstration (krav) – ikke bygget", async ({ page }) => {
  test.info().annotations.push({ type: "not-implemented", description: "/proev har chat + tilbageringning, men ingen kampagnedemo." });
  await open(page);
  await expect(page.locator("main")).not.toContainText(/kampagne/i);
});
