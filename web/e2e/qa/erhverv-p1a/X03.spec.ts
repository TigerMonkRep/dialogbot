import { expect, test, type Page } from "@playwright/test";
import { evid, noHorizontalScroll, smsCodeFor, snap, uniqueIp, uniqueMobile } from "./p1a-helpers";

/* QA X03 (e2e-erhverv A, wave 2): /start – the Erhverv quiz-funnel against the FULL stack (real backend, fake adapters).
 * Requirement: spørgsmål → profil opbygges i baggrunden → reveal bag navn/e-mail; lead gemmes én gang; tilbage/genindlæs
 * midt i. Source: web/src/app/start/erhverv-steps.tsx, components/funnel/*, app/modules/funnel/service.py.
 * The backend half (lead once, existing e-mail) is tests/qa/test_qa_X03.py. */
const ID = "X03";
evid(ID);

test.beforeEach(async ({ page }) => { await page.setExtraHTTPHeaders({ "x-real-ip": uniqueIp() }); });

async function toStep5(page: Page, company: string) {
  await page.goto("/start");
  await expect(page).toHaveURL(/\/start\/1/);
  await expect(page.getByText("Trin 1 af 7").first()).toBeVisible();
  await page.getByRole("radio", { name: "Håndværker" }).click();
  await expect(page).toHaveURL(/\/start\/2$/);
  await page.getByRole("combobox").fill(company);
  await page.keyboard.press("Escape");
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/start\/3$/);
  await page.getByRole("checkbox", { name: "Til frokost" }).click();
  await expect(page.locator("[data-estimate]")).toBeVisible();
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/start\/4$/);
  await expect(page.locator("[data-next]")).toBeDisabled();
  await page.getByRole("checkbox", { name: /Booke tider/ }).click();
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/start\/5$/);
}

test.setTimeout(120_000);

test("X03 · fuld vej: 7 trin → kode → reveal; leadet gemmes én gang; ingen konto før koden", async ({ page }, info) => {
  const company = `QA Tømrer ${info.project.name} ${Date.now()}`;
  const mobile = uniqueMobile();
  const email = `e2a-x03-${info.project.name}-${Date.now()}@example.com`;
  await toStep5(page, company);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(company);
  await expect(page.locator("[data-row='voice']")).toHaveAttribute("data-state", "done", { timeout: 30_000 });
  await expect(page.locator("[data-next]")).toBeEnabled({ timeout: 45_000 });
  await noHorizontalScroll(page);
  await snap(page, info, ID, "trin5-profil");
  // Nothing exists yet: no session.
  expect((await page.request.get("/api/backend/auth/me")).status()).toBe(401);
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/start\/6$/);

  // Gate: validation per field
  await page.locator("[data-next]").click();
  await expect(page.locator("[data-gate='name']")).toBeVisible();
  await page.getByLabel("Navn").fill("Mette Larsen");
  await page.locator("[data-next]").click();
  await page.getByLabel("Mobil").fill("123");
  await page.locator("[data-next]").click();
  await expect(page.locator("[data-gate='phone']")).toBeVisible(); // invalid number stays
  await page.getByLabel("Mobil").fill(mobile);
  await page.locator("[data-next]").click();
  await page.getByLabel("E-mail").fill(email);
  await page.locator("[data-next]").click();
  await expect(page.locator("[data-gate='consent']")).toBeVisible();
  await page.getByRole("checkbox", { name: /Dialogbot/ }).check();
  await snap(page, info, ID, "trin6-gate");
  // double submit: one SMS, no error
  await page.locator("[data-next]").dblclick();
  await expect(page).toHaveURL(/\/start\/7$/, { timeout: 15_000 });
  const code = await smsCodeFor(`+45${mobile}`);
  await page.getByLabel("Kode fra SMS").fill(code === "000000" ? "111111" : "000000");
  await expect(page.locator("#code-hint")).toContainText(/passer ikke/);
  await page.getByLabel("Kode fra SMS").fill(code);
  await expect(page).toHaveURL(/\/start\/klar/, { timeout: 20_000 });
  await snap(page, info, ID, "klar");
  await noHorizontalScroll(page);

  // Lead stored once: exactly one account with exactly one workspace named after the company.
  const me = await (await page.request.get("/api/backend/auth/me")).json();
  expect(me.email).toBe(email);
  const ws = (await (await page.request.get("/api/backend/workspaces")).json()) as { name: string }[];
  expect(ws.map((w) => w.name)).toEqual([company]);
  // Honest reveal: when the backend says no call was placed (call=null + call_problem), the page must not claim one is
  // on its way (F-E2A-03). Source: app/modules/funnel/service.py reveal(), web/src/app/start/klar/klar.tsx.
  const draftId = (await page.context().cookies()).find((c) => c.name === "dialogbot_funnel")?.value;
  expect(draftId).toBeTruthy();
  const rv = await (await page.request.get(`/api/backend/funnel/drafts/${draftId}/reveal`)).json();
  await info.attach("reveal.json", { body: JSON.stringify(rv, null, 2), contentType: "application/json" });
  if (rv.call === null && rv.call_problem) {
    await page.waitForTimeout(4000);
    await snap(page, info, ID, "klar-uden-opkald");
    await expect(page.getByText("Opkaldet er på vej"), `backend: ${rv.call_problem}`).toHaveCount(0);
  }
  // Reload of the reveal keeps the state and does not create anything again.
  await page.reload();
  await expect(page).toHaveURL(/\/start\/klar/);
  expect(((await (await page.request.get("/api/backend/workspaces")).json()) as unknown[]).length).toBe(1);
});

test("X03 · dybt link til et senere trin for en ny besøgende springer ikke spørgsmål 1 over", async ({ page }, info) => {
  await page.goto("/start/4");
  // Nothing answered yet: question 1 (branche) must not be skipped (F-E2A-02; e2e/funnel.spec.ts expects the same).
  await page.waitForTimeout(1500);
  await snap(page, info, ID, "dybt-link");
  await expect(page).toHaveURL(/\/start\/1$/);
});

test("X03 · tilbage og genindlæs midt i: svarene står der stadig; gaten kan ikke nås før spørgsmålene", async ({ page }, info) => {
  await page.goto("/start/1");
  const company = `QA Klinik ${Date.now()}`;
  await page.getByRole("radio", { name: "Håndværker" }).click();
  await page.getByRole("combobox").fill(company);
  await page.keyboard.press("Escape");
  await page.locator("[data-next]").click();
  await expect(page).toHaveURL(/\/start\/3$/);
  await page.getByRole("checkbox", { name: "Efter kl. 16" }).click();
  await expect(page.locator("[data-estimate]")).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/start\/3$/);
  await expect(page.getByRole("checkbox", { name: "Efter kl. 16" })).toHaveAttribute("aria-checked", "true");
  await page.goBack();
  await expect(page).toHaveURL(/\/start\/2$/);
  await expect(page.getByRole("combobox")).toHaveValue(company);
  await page.goto("/start/6");
  await expect(page).toHaveURL(/\/start\/(3|4)$/); // the gate is not reachable before the questions are answered
  await snap(page, info, ID, "genindlaes");
});

test("X03 · serverfejl ved kladden viser fejl og «prøv igen», ikke en hvid side", async ({ page }, info) => {
  await page.route("**/api/backend/funnel/drafts**", (r) => r.request().method() === "POST" || r.request().method() === "GET"
    ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "boom" }) })
    : r.continue());
  await page.context().clearCookies();
  await page.goto("/start/1");
  await expect(page.getByRole("button", { name: "Start forfra" })).toBeVisible({ timeout: 15_000 });
  await snap(page, info, ID, "serverfejl");
  await page.unrouteAll();
  await page.getByRole("button", { name: "Start forfra" }).click();
  await expect(page.getByRole("radio", { name: "Håndværker" })).toBeVisible({ timeout: 15_000 });
});

test("X03 · SMS-fejl (502) ved koden: personen bliver på trinnet med en forståelig besked", async ({ page }, info) => {
  await toStep5(page, `QA SMS ${Date.now()}`);
  await expect(page.locator("[data-next]")).toBeEnabled({ timeout: 45_000 });
  await page.locator("[data-next]").click();
  await page.route("**/gate", (r) => r.fulfill({ status: 502, contentType: "application/json",
    body: JSON.stringify({ code: "sms_failed", message: "SMS kunne ikke sendes lige nu. Prøv igen om lidt." }) }));
  await page.getByLabel("Navn").fill("Mette Larsen"); await page.locator("[data-next]").click();
  await page.getByLabel("Mobil").fill(uniqueMobile()); await page.locator("[data-next]").click();
  await page.getByLabel("E-mail").fill(`e2a-x03-sms-${Date.now()}@example.com`); await page.locator("[data-next]").click();
  await page.getByRole("checkbox", { name: /Dialogbot/ }).check();
  await page.locator("[data-next]").click();
  await expect(page.getByText(/SMS kunne ikke sendes/)).toBeVisible();
  await expect(page).toHaveURL(/\/start\/6$/);
  await snap(page, info, ID, "sms-fejl");
});
