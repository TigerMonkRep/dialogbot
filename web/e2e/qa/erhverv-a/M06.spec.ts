import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* QA M06 (e2e-erhverv A): /admin/support – support queue, ticket detail, assignment, client-visible replies.
 * The operator admin lives at /app/operator/admin (web/src/app/app/(admin)/operator/admin/shared.tsx TABS);
 * the queue is /app/operator/admin/support (/admin/support redirects there), API app/modules/support/operator_router.py. */
const EVID = "../qa/evidence/M06";
const CSRF = { "x-requested-with": "dialogbot" };

test("M06 · operatørens supportkø findes", async ({ page }, info) => {
  await freshOwner(page, info);
  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/admin");
  const tabs = await page.getByRole("navigation", { name: "Admin" }).getByRole("link").allInnerTexts();
  info.annotations.push({ type: "admin-tabs", description: tabs.join(", ") });
  await page.screenshot({ path: `${EVID}/${info.project.name}-admin-faner.png`, fullPage: true });
  const statuses: Record<string, number | undefined> = {};
  for (const p of ["/admin/support", "/app/operator/support", "/app/operator/admin/support"]) statuses[p] = (await page.request.get(p)).status();
  info.annotations.push({ type: "routes", description: JSON.stringify(statuses) });
  expect(tabs.some((t) => /support/i.test(t)) || Object.values(statuses).some((s) => s === 200), `no support queue: tabs=${tabs.join("|")} routes=${JSON.stringify(statuses)}`).toBeTruthy();
  expect(tabs).toContain("Support");
  expect(Object.values(statuses).every((s) => s === 200), JSON.stringify(statuses)).toBeTruthy();
});

test("M06 · kø, tildeling, kundesynligt svar og intern note (DB-016)", async ({ browser }, info) => {
  // the customer opens a ticket
  const customerCtx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined });
  const customer = await customerCtx.newPage();
  const { wsId } = await freshOwner(customer, info);
  const subject = `SIP-kvote ${info.project.name} ${Date.now()}`;
  const created = await customer.request.post(`/api/backend/workspaces/${wsId}/support/tickets`, {
    headers: CSRF, multipart: { subject, category: "reception", body: "Kan vi få flere samtidige linjer?" } });
  expect(created.status()).toBe(201);
  const number = (await created.json()).number as number;
  // a customer is not an operator
  expect((await customer.request.get("/api/backend/operator/support/tickets")).status()).toBe(403);
  await customer.goto("/app/operator/admin/support");
  await expect(customer.getByText("Admin er kun for Dialogbot-operatører.")).toBeVisible();

  // the operator works the queue
  const opCtx = await browser.newContext({ viewport: info.project.use.viewport ?? undefined });
  const op = await opCtx.newPage();
  await freshOwner(op, info);
  expect((await op.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await op.goto("/admin/support");
  await expect(op).toHaveURL(/\/app\/operator\/admin\/support/);
  await op.getByLabel("Søg").fill(subject);
  await op.getByRole("button", { name: "Filtrér" }).click();
  await op.getByRole("link", { name: new RegExp(subject) }).click();
  await expect(op.getByRole("heading", { level: 1, name: subject })).toBeVisible();
  await op.screenshot({ path: `${EVID}/${info.project.name}-sag-foer.png`, fullPage: true });

  // assign to me, priority high
  const me = op.getByLabel("Tildelt operatør");
  const myId = (await (await op.request.get("/api/backend/auth/me")).json()).id as string;
  await me.selectOption(myId);
  await op.getByLabel("Prioritet").selectOption("high");
  await op.getByRole("button", { name: "Gem behandling" }).click();
  await expect(op.locator("[data-priority]").first()).toHaveText("Høj");

  // internal note, then a client-visible reply
  const secret = `INTERN ${Date.now()}: kunden har 4 linjer i aftalen`;
  await op.getByLabel("Intern note (fortrolig)").check();
  await op.getByLabel("Intern note", { exact: true }).fill(secret);
  await op.getByRole("button", { name: "Gem intern note" }).click();
  await expect(op.locator('[data-visibility="internal"]')).toContainText(secret);
  await op.getByLabel("Kundesynligt svar").check();
  const reply = "Hej. Vi har hævet kvoten til 8 linjer – prøv igen.";
  await op.getByLabel(/^Svar til /).fill(reply);
  await op.getByRole("button", { name: "Send svar til kunde" }).click();
  await expect(op.locator('[data-visibility="public"]').last()).toContainText(reply);
  await expect(op.locator("[data-status]").first()).toHaveText("Afventer kunde");
  await op.screenshot({ path: `${EVID}/${info.project.name}-sag-efter.png`, fullPage: true });

  // «Tildelt mig» lists it
  await op.goto("/app/operator/admin/support?status=active&assigned=me");
  await expect(op.getByRole("link", { name: new RegExp(subject) })).toBeVisible();

  // the customer sees the reply, never the internal note – neither on the page nor in the API
  await customer.goto(`/app/support/${number}`);
  await expect(customer.getByText(reply)).toBeVisible();
  await expect(customer.getByText("Vi har svaret. Skriv tilbage, eller markér sagen som løst.")).toBeVisible();
  expect(await customer.locator("body").innerText()).not.toContain(secret);
  const api = await customer.request.get(`/api/backend/workspaces/${wsId}/support/tickets/${number}`);
  expect(await api.text()).not.toContain(secret);
  expect(await (await customer.request.get(`/api/backend/workspaces/${wsId}/audit`)).text()).not.toContain(secret);
  await customer.screenshot({ path: `${EVID}/${info.project.name}-kunde-ser-svar.png`, fullPage: true });
  await customerCtx.close();
  await opCtx.close();
});
