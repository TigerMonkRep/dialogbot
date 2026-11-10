import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { DEMO_PASSWORD, freshOwner, latestMailLink, skipSetupGate, uniqueEmail } from "../../helpers";

/* QA A06 (e2e-erhverv A): /onboarding/workspace (→ /opsaetning/1) – create the business workspace or choose an
 * existing one; the product intent is saved. Source: web/src/app/opsaetning/1/{page,step1}.tsx,
 * web/src/lib/workspace.server.ts, web/src/components/shell.client.tsx (WorkspaceChip). */
const EVID = "../qa/evidence/A06";
const CSRF = { "x-requested-with": "dialogbot" };

async function verifiedNoWorkspace(page: Page, info: TestInfo, intent: string, verify = true) {
  const email = uniqueEmail(`a06${intent}`, info);
  expect((await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: "QA A06", signup_intent: intent } })).status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  if (verify) {
    const token = (await latestMailLink(page.request, /token=[\w-]+/)).split("=")[1];
    expect((await page.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  }
  await skipSetupGate(page);
  return email;
}
const myWorkspaces = async (page: Page) => (await (await page.request.get("/api/backend/workspaces")).json()) as { id: string; name: string; product_intent: string }[];

test("A06 · ubekræftet kan ikke oprette; bekræftet opretter ét arbejdsrum (også ved dobbeltklik) med hensigten fra tilmeldingen", async ({ page }, info) => {
  await verifiedNoWorkspace(page, info, "both", false);
  await page.goto("/onboarding/workspace");
  await expect(page).toHaveURL(/\/opsaetning\/1$/);
  await expect(page.getByText("Bekræft din e-mail først.")).toBeVisible();
  await page.getByLabel("Navn (som den siger det)").fill("QA Ubekræftet ApS");
  await expect(page.getByRole("button", { name: "Videre" })).toBeDisabled();
  await page.screenshot({ path: `${EVID}/${info.project.name}-ubekraeftet.png`, fullPage: true });

  await page.context().clearCookies();
  await verifiedNoWorkspace(page, info, "campaigns");
  await page.goto("/onboarding/workspace");
  await expect(page).toHaveURL(/\/opsaetning\/1$/);
  const name = `QA A06 ${info.project.name} ${Date.now()}`;
  await page.getByLabel("Navn (som den siger det)").fill(name);
  await page.getByRole("button", { name: "Videre" }).dblclick();
  await expect(page.getByRole("checkbox", { name: /Ringe kunder op/ })).toBeChecked({ timeout: 20_000 });
  await expect(page.getByRole("checkbox", { name: /Tage telefonen/ })).not.toBeChecked();
  const list = await myWorkspaces(page);
  expect(list.map((w) => w.name), "double click must not create two workspaces").toEqual([name]);
  expect(list[0].product_intent).toBe("campaigns");
  await page.reload();
  await expect(page.getByLabel("Navn (som den siger det)")).toHaveValue(name);
  await page.screenshot({ path: `${EVID}/${info.project.name}-oprettet.png`, fullPage: true });
});

test("A06 · vælg et eksisterende arbejdsrum; et fremmed arbejdsrum-id i cookien giver aldrig adgang", async ({ page, browser, context }, info) => {
  // a stranger's workspace
  const other = await browser.newContext({ baseURL: info.project.use.baseURL });
  const foreign = await freshOwner(await other.newPage(), info);
  await other.close();
  const me = await freshOwner(page, info, "reception");
  const second = await (await page.request.post("/api/backend/workspaces", { headers: CSRF, data: { name: `QA A06 anden ${Date.now()}`, product_intent: "both" } })).json();
  // choose via the chip in the app shell
  await page.goto("/app/konto");
  const chip = page.getByRole("button", { name: /^Arbejdsrum: / });
  await expect(chip, "a person with two workspaces must be able to choose one on this viewport").toBeVisible({ timeout: 5_000 });
  await chip.click();
  await page.getByRole("option").filter({ hasText: second.name }).getByRole("button").click();
  await expect.poll(async () => (await context.cookies()).find((c) => c.name === "db_ws")?.value).toBe(second.id);
  await page.screenshot({ path: `${EVID}/${info.project.name}-vaelg.png`, fullPage: true });
  // tampered cookie: the stranger's id must fall back to the user's own workspace, never show the stranger's
  const base = info.project.use.baseURL ?? "http://localhost:3000";
  await context.addCookies([{ name: "db_ws", value: foreign.wsId, url: base }]);
  await page.goto("/app/konto");
  const body = await page.locator("main").innerText();
  const foreignName = `E2E ${info.project.name}`;
  expect(body).not.toContain(foreign.wsId);
  const r = await page.request.get(`/api/backend/workspaces/${foreign.wsId}/members`);
  expect(r.status()).toBe(404);
  expect((await myWorkspaces(page)).map((w) => w.id).sort()).toEqual([me.wsId, second.id].sort());
  void foreignName;
});
