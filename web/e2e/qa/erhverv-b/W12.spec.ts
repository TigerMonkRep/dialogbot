import { expect, test } from "@playwright/test";
import { freshOwner, serve } from "../../helpers";
import { smsCodeFor } from "../erhverv-p1a/p1a-helpers";

/* QA W12 (e2e-erhverv B): booking in the customer-facing widget – details, consent, explicit submit, confirmed and
 * slot-lost states, double click. Own port (4127) so parallel agents using :4000 are not disturbed. */
const CSRF = { "x-requested-with": "dialogbot" };
const SITE = "http://localhost:4127";
const servers: import("node:http").Server[] = [];
test.afterEach(async () => { while (servers.length) await new Promise((r) => servers.pop()!.close(r)); });

test("W12 · kunden booker i widgetten: samtykke kræves, bekræftet, tiden-taget og dobbeltklik giver én booking", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const week = [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], open: "08:00", close: "20:00" }];
  for (const [kind, title, content] of [["opening_hours", "Åbningstider", { weekly: week }], ["service", "Gulvafslibning", {}]] as const) {
    const item = await (await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/items`, { headers: CSRF, data: { kind, title, content } })).json();
    await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/submit`, { headers: CSRF });
    expect((await page.request.post(`/api/backend/workspaces/${wsId}/knowledge/versions/${item.open_draft.id}/approve`, { headers: CSRF })).ok()).toBeTruthy();
  }
  await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } });
  const s = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/settings`)).json();
  expect((await page.request.put(`/api/backend/workspaces/${wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: s.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 } })).ok()).toBeTruthy();
  // the chat answers visitors only with a paid subscription (Fürster 12/11); no Stripe in E2E: confirmed = paid
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } })).ok()).toBeTruthy();
  const wc = await (await page.request.get(`/api/backend/workspaces/${wsId}/webchat`)).json();
  const w = await (await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: wc.version, enabled: true, allowed_origins: [SITE], greeting: "" } })).json();
  servers.push(await serve(4127, `<!doctype html><html lang="da"><head><title>Kundeside</title></head><body><h1>Fjord Gulv</h1>${w.embed_code}</body></html>`));

  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const [a, b] = [await ctx.newPage(), await ctx.newPage()];
  for (const p of [a, b]) { await p.goto(`${SITE}/`); await p.getByRole("button", { name: "Åbn chat" }).click(); }
  const chatA = a.frameLocator('iframe[title^="Chat med"]'), chatB = b.frameLocator('iframe[title^="Chat med"]');
  for (const chat of [chatA, chatB]) await chat.getByRole("button", { name: "Book en tid" }).click();
  const formA = chatA.locator("form.book"), formB = chatB.locator("form.book");
  const first = await formA.getByLabel("Tidspunkt").locator("option").first().getAttribute("value");
  // details and consent are required
  await formA.getByLabel("Navn").fill("Henrik Villumsen");
  await formA.getByLabel("Telefon").fill("+45 20 30 40 50");
  await formA.getByRole("button", { name: "Book", exact: true }).click();
  await expect(formA.getByText("Sæt flueben, så virksomheden må kontakte dig om aftalen.")).toBeVisible();
  await formA.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
  // double click on Book: exactly one booking must exist
  await formA.getByRole("button", { name: "Book", exact: true }).dblclick();
  // W04 on the booking door (F-VER1113-04): one code step for the double click, then exactly one booking
  await expect(chatA.locator(".code-step")).toBeVisible();
  await chatA.locator(".code-step").getByLabel("Kode fra SMS").fill(await smsCodeFor("+4520304050"));
  await chatA.locator(".code-step").getByRole("button", { name: "Bekræft" }).click();
  await expect(chatA.getByText(/Tak, Henrik Villumsen! Du er booket .+kl\./)).toBeVisible();
  await a.screenshot({ path: `../qa/evidence/W12/${info.project.name}-booket.png` });
  // the second visitor still sees the old list: picking the same time gives the slot-lost state and a fresh list
  await formB.getByLabel("Tidspunkt").selectOption(first!);
  await formB.getByLabel("Navn").fill("Anden Kunde");
  await formB.getByLabel("E-mail").fill("anden@example.com");
  await formB.getByLabel("Virksomheden må kontakte mig om aftalen.").check();
  await formB.getByRole("button", { name: "Book", exact: true }).click();
  await expect(formB.getByText("Tiden blev lige taget – vælg en anden.")).toBeVisible();
  await expect(formB.getByLabel("Tidspunkt").locator(`option[value="${first}"]`)).toHaveCount(0);
  await b.screenshot({ path: `../qa/evidence/W12/${info.project.name}-tiden-taget.png` });
  await ctx.close();
  const list = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings?days=14`)).json();
  expect(list.items.length).toBe(1);
  expect(list.items[0].contact_name).toBe("Henrik Villumsen");
});
