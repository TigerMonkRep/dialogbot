import { expect, test, type Page } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { CSRF, campaignOwner, evid, importCsv, newCampaign, sql } from "../erhverv-c/e2c-helpers";

/* Launch requirements C09, C15, B03, B04, B05, M04 in the one-plan model A' (Fürster 2026-11-10; scenarios rewritten
 * 2026-11-12, fix-engineer #26). The numbers are worked out from the price rules, the same month as
 * tests/qa/test_qa_launch_billing.py: 300 package minutes for inbound + outbound together, then 1,50 kr./2,00 kr. per
 * started minute, and 4 / 1 / 0,25 kr. for an outbound call that starts after the package (excl. VAT).
 * The calls are seeded as data rows (the stack has no telephony); everything shown is read through the real API. */

const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
const id = (out: string) => out.trim().split("\n")[0];

/** This month, in call order (minutes before now):
 *  in1 290 min · A answered 5:30 (6 min) · in2 61 s (2) · B answered 3:01 (4: 2 in the package, 2 over = 4,00) ·
 *  C voicemail (1,00) · D unanswered (0,25) · E no report yet (0,25, pending) · in3 2:05 (3 over = 4,50).
 *  Package 305 of 300, 5 over; usage 10,00 kr.; month 2.505,00 + 626,25 VAT = 3.131,25 kr. */
async function seedMonth(page: Page, wsId: string) {
  test.skip(new Date(ago(12)).toLocaleDateString("da-DK", { timeZone: "Europe/Copenhagen", month: "numeric" })
    !== new Date().toLocaleDateString("da-DK", { timeZone: "Europe/Copenhagen", month: "numeric" }), "the month just turned");
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } })).status()).toBe(201);
  const camp = await newCampaign(page.request, wsId, "Vinterkampagne");
  await importCsv(page.request, wsId, camp.id, "Navn;Telefon\nA;20304050\nB;20304051\nC;20304052\nD;20304053\nE;20304054");
  const contacts = sql(`select id from campaign_contacts where campaign_id='${camp.id}' order by phone`).trim().split("\n");
  const inbound = (name: string, min: number, sec: number) => id(sql(`insert into calls (id, workspace_id, provider, provider_call_id, started_at, duration_seconds, from_number, summary)
    values (gen_random_uuid(), '${wsId}', 'vapi', 'qa-lb-${name}-${Date.now()}', '${ago(min)}', ${sec}, '+4540000000', '') returning id`));
  const outbound = (i: number, min: number, sec: number | null, outcome: string | null) => id(sql(`insert into campaign_calls (id, workspace_id, campaign_id, contact_id, provider_call_id, dialled_at, net_minor, connected_seconds, outcome_class)
    values (gen_random_uuid(), '${wsId}', '${camp.id}', '${contacts[i]}', 'qa-lb-out${i}-${Date.now()}', '${ago(min)}', 0, ${sec ?? "null"}, ${outcome ? `'${outcome}'` : "null"}) returning id`));
  const r = { in1: inbound("in1", 11, 290 * 60), A: outbound(0, 10, 330, "answered"), in2: inbound("in2", 9, 61),
    B: outbound(1, 8, 181, "answered"), C: outbound(2, 7, 0, "voicemail"), D: outbound(3, 6, 0, "no_answer"),
    E: outbound(4, 5, null, null), in3: inbound("in3", 4, 125) };
  return { ...r, campaignId: camp.id as string };
}

const row = (page: Page, callId: string) => page.locator(`li[data-call="${callId}"]`);

test("C09 · kampagnestart: ærligt maks.-beløb netto/brutto og kræver betalt abonnement med vej til Konto", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA C09 ${info.project.name}`);
  await importCsv(page.request, wsId, c.id, "Navn;Telefon\nMette;20304050\nOle;21222324\nBo;22334455");
  await page.goto(`/app/kampagner/${c.id}`);
  // 3 contacts × (2 attempts × 4 kr. + 3 min × 2 kr.) = 42 kr. excl. VAT, 52,50 incl. VAT (14 kr. per contact)
  await expect(page.getByRole("heading", { name: "3 kontakter · højst 42,00 kr. ekskl. moms" })).toBeVisible();
  await expect(page.getByText(/højst 14,00 kr\. pr\. kontakt\) er prisen højst 42,00 kr\. \+ moms \(52,50 kr\. inkl\. moms\)/)).toBeVisible();
  const needs = page.getByTestId("needs-subscription");
  await expect(needs).toContainText("Kampagnen kan startes, når abonnementet er bekræftet og der er et betalingskort på kontoen.");
  await expect(needs.getByRole("link", { name: "Gå til Konto" })).toHaveAttribute("href", "/app/konto#abonnement");
  const boxes = page.locator("aside fieldset input[type=checkbox]");
  for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).check();
  await expect(page.getByRole("button", { name: "Start kampagne" })).toBeDisabled();
  await page.screenshot({ path: evid("C09", info, "kraever-abonnement"), fullPage: true });
  const start = await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/start`, { headers: CSRF,
    data: { expected_version: c.version, legal_confirmed: true, accept_max_net_minor: 4200 } });
  expect(start.status()).toBe(409);
  expect((await start.json()).code).toBe("subscription_required");
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/start`, { headers: CSRF,
    data: { expected_version: c.version, legal_confirmed: true, accept_max_net_minor: 4199 } })).status()).toBe(409);
  // the owner confirms the subscription (no card payment set up in this stack = paid): the hint goes away
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/agreement`, { headers: CSRF, data: { model: "A" } })).status()).toBe(201);
  await page.reload();
  await expect(page.getByTestId("needs-subscription")).toHaveCount(0);
  expect((await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns/${c.id}`)).json()).status).toBe("draft");
});

test("B03 · B05 · C15 · forbrug pr. opkald i den fælles pakke, månedens tal og afventende rapport", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const r = await seedMonth(page, wsId);
  await page.goto("/app/konto");
  // B05: the month so far – package used/left/over and the amounts incl. the call prices after the package
  await expect(page.getByTestId("package-left")).toHaveText("0 minutter tilbage i pakken denne måned");
  await expect(page.getByText("5 påbegyndte minutter ud over pakken · 10,00 kr. ekskl. moms.")).toBeVisible();
  await expect(page.getByText("Denne måned: 5 opkald, 10 samtaleminutter · 5,50 kr. ekskl. moms")).toBeVisible();
  await expect(page.getByText(/indtil videre: 2\.505,00 kr\. ekskl\. moms · moms 626,25 kr\. · i alt 3\.131,25 kr\./)).toBeVisible();
  // B03: every call with duration, started minutes, package / over, outcome, price
  await expect(page.getByTestId("usage-package")).toHaveText("Minutpakke: 305 af 300 minutter brugt · 0 tilbage · 5 minutter ud over pakken.");
  await expect(row(page, r.A)).toContainText("varighed 5:30");
  await expect(row(page, r.A).getByTestId("usage-split")).toContainText("6 min i pakken");
  await expect(row(page, r.B).getByTestId("usage-split")).toContainText("2 min i pakken · 2 min ud over pakken");
  await expect(row(page, r.B)).toContainText(/i alt 4(,00)? kr\. ekskl\. moms/);
  await expect(row(page, r.C)).toContainText("telefonsvarer");
  await expect(row(page, r.C)).toContainText(/opkaldspris efter pakken 1(,00)? kr\./);
  await expect(row(page, r.D)).toContainText("ubesvaret/optaget");
  await expect(row(page, r.D)).toContainText("i alt 0,25 kr. ekskl. moms");
  await expect(row(page, r.E).getByTestId("usage-pending")).toHaveText("Afventer opkaldsrapport – minutterne tælles med, når den kommer.");
  await expect(row(page, r.in3)).toContainText("3 min ud over pakken");
  await expect(row(page, r.in3)).toContainText("i alt 4,50 kr. ekskl. moms");
  await expect(row(page, r.in1)).toContainText("290 min i pakken");
  await expect(page.locator("li[data-call]").getByRole("button", { name: "Klag over opkaldet" })).toHaveCount(8);
  await page.locator("#forbrug").screenshot({ path: evid("B03", info, "forbrug-pr-opkald") });
  // C15: the campaign shows the call without a report as awaiting, from the same source as the statement
  await page.goto(`/app/kampagner/${r.campaignId}`);
  await expect(page.getByTestId("awaiting-report")).toHaveText("1 opkald afventer opkaldsrapporten – minutterne tælles med, når den kommer.");
  const camp = await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns/${r.campaignId}`)).json();
  const st = await (await page.request.get(`/api/backend/workspaces/${wsId}/billing/statement`)).json();
  expect(camp.counts.calls).toBe(st.lines.find((l: { kind: string }) => l.kind === "campaign_calls").calls);
  await page.screenshot({ path: evid("C15", info, "afventer-rapport"), fullPage: true });
  // B05: an invoiced month shows its frozen lines, totals and what Stripe refunded (seeded invoice for this month)
  const month = st.month as string;
  sql(`insert into invoices (id, workspace_id, month, status, currency, number, net_minor, tax_minor, gross_minor, lines, refunds)
    values (gen_random_uuid(), '${wsId}', '${month}-01', 'paid', 'DKK', 'QA-B05-${Date.now() % 100000}', ${st.totals.net_minor}, ${st.totals.tax_minor}, ${st.totals.gross_minor},
    '${JSON.stringify(st.lines).replace(/'/g, "''")}'::jsonb, '{"charges": {"ch_qa": 10000}, "credit_notes": {"cn_qa": 10000}, "applied_minor": 10000}'::jsonb)`);
  await page.goto("/app/konto");
  const inv = page.getByTestId("usage-invoice");
  await expect(inv).toContainText("Måneden er faktureret");
  await expect(inv).toContainText(/2\.505(,00)? kr\. ekskl\. moms · moms 626,25 kr\. · i alt 3\.131,25 kr\./);
  await expect(inv).toContainText(/Refunderet hos Stripe: 100(,00)? kr\. inkl\. moms\./);
  await expect(inv).toContainText(/opkald efter brugt pakke – 1 telefonsvarer à 1(,00)?\skr\., 2 ubesvaret\/optaget à 0,25\skr\./);
  await inv.screenshot({ path: evid("B05", info, "faktureret-periode") });
});

test("B04 · M04 · klage over et opkald → operatøren godkender med begrundelse → minutterne tilbage i pakken; operatørens fakturaoverblik", async ({ page, browser }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const r = await seedMonth(page, wsId);
  await page.goto("/app/konto");
  const b = row(page, r.B);
  await b.getByRole("button", { name: "Klag over opkaldet" }).click();
  await b.getByLabel("Hvad var galt med opkaldet?").fill("Ringede til en, der havde frabedt sig opkald");
  await b.getByRole("button", { name: "Send klage" }).click();
  await expect(b.getByRole("status")).toHaveText("Klage sendt – Dialogbot behandler den.");
  const dispute = (await (await page.request.get(`/api/backend/workspaces/${wsId}/billing/disputes`)).json()).items[0];

  const opCtx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const op = await opCtx.newPage();
  await freshOwner(op, info);
  expect((await op.request.post("/api/backend/dev/operator/self", { headers: CSRF, data: {} })).ok()).toBeTruthy();
  await op.goto("/app/operator/admin/fakturering");
  // M04: the price list with its version, per currency
  const dkk = op.getByTestId("price-list").locator('tr[data-currency="DKK"]');
  await expect(op.getByTestId("price-list")).toContainText("Prisliste (version 2026-11-10, gælder fra 2026-11-01)");
  await expect(dkk).toContainText("2.495,00");
  await expect(dkk).toContainText("4,00 / 1,00 / 0,25");
  await expect(op.getByTestId("price-list").locator('tr[data-currency="EUR"]')).toBeVisible();
  // M04: the customer – agreement snapshot with the call prices, usage inbound/outbound apart (DB-004), the reconciliation
  const cust = op.locator(`tr[data-customer="${wsId}"]`);
  await expect(cust).toContainText("opkald 4,00 kr./1,00 kr./0,25 kr.");
  await expect(cust).toContainText("305 af 300 min · 0 tilbage");
  await expect(cust).toContainText("3 opkald, 295 min ind");
  await expect(cust).toContainText("5 kampagneopkald, 10 min ud · 1 afventer rapport");
  await expect(cust).toContainText("5 min · 10,00 kr.");
  await expect(cust).toContainText("heraf opkaldspriser 1,50 kr.");
  await expect(cust.getByTestId("reconciliation")).toHaveText("Ingen afvigelser");
  // B04: the complaint in the queue; approve with a note
  const q = op.locator(`li[data-dispute="${dispute.id}"]`);
  await expect(q).toContainText("Kampagne");
  await expect(q).toContainText("4 min");
  await expect(q).toContainText("måneden er ikke faktureret – godkendelse giver minutterne tilbage i pakken");
  await op.screenshot({ path: evid("M04", info, "fakturering"), fullPage: true });
  await q.getByLabel("Note til afgørelsen").fill("Fejl i spærrelisten");
  await q.getByRole("button", { name: "Godkend" }).click();
  await expect(op.locator(`li[data-dispute="${dispute.id}"]`)).toHaveCount(0);
  await expect(cust).toContainText("301 af 300 min · 0 tilbage");
  await opCtx.close();

  // the customer sees the decision and the reason; the 4 minutes are back: 301 used, 1 over, no call prices any more
  await page.reload();
  await expect(row(page, r.B).getByRole("status")).toContainText("Klagen er godkendt – minutterne er tilbage i pakken.");
  await expect(row(page, r.B).getByRole("status")).toContainText("Dialogbots begrundelse: Fejl i spærrelisten");
  await expect(page.getByTestId("usage-package")).toHaveText("Minutpakke: 301 af 300 minutter brugt · 0 tilbage · 1 minutter ud over pakken.");
  await expect(page.getByText("1 påbegyndte minutter ud over pakken · 1,50 kr. ekskl. moms.")).toBeVisible();
  await expect(row(page, r.C)).not.toContainText("opkaldspris efter pakken");
  await page.locator("#forbrug").screenshot({ path: evid("B04", info, "klage-godkendt") });
});
