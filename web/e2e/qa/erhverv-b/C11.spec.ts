import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* QA C11 (e2e-erhverv B): final readiness and explicit launch confirmation – no automatic launch (DB-018). */
const CSRF = { "x-requested-with": "dialogbot" };
const EVID = "../qa/evidence/C11";

test("C11 · kampagne kan ikke startes uden bekræftelse og opsat udgående telefoni; ingen Staging-mærkat", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info, "campaigns");
  const goals = await (await page.request.get(`/api/backend/workspaces/${wsId}/goals`)).json();
  const { version, ...g } = goals;
  await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...g, callback: true, expected_version: version } }); // best effort; the page lists existing campaigns anyway
  const c = await (await page.request.post(`/api/backend/workspaces/${wsId}/campaigns`, { headers: CSRF, data: { name: `QA-EB C11 ${info.project.name}`, purpose: "Tilbyde gulvafslibning til tidligere kunder" } })).json();
  const imp = await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/contacts/import`, { headers: CSRF,
    data: { csv: "Navn;Telefon\nMette Hansen;20304050\nOle Berg;21222324", kind: "business", consent_source: "Tilmelding på hjemmesiden, marts 2026" } });
  expect(imp.ok()).toBeTruthy();

  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByRole("heading", { name: c.name })).toBeVisible();
  const start = page.getByRole("button", { name: "Start kampagne" });
  await expect(start).toBeDisabled();
  // tick every legal checkbox: still disabled because outbound telephony is not set up – said honestly
  const boxes = page.locator("aside fieldset input[type=checkbox]");
  for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).check();
  await expect(page.getByText(/Udgående opkald er ikke sat op|Vælg hvilket af jeres telefonnumre|ikke klar endnu|ikke godkendt til udgående/).first()).toBeVisible();
  await expect(start).toBeDisabled();
  await expect(page.getByText("Betaling starter aldrig opkald", { exact: false })).toBeVisible();
  // business rule: no "Staging" label anywhere in the logged-in UI
  expect(await page.locator("body").innerText()).not.toMatch(/staging/i);
  await page.screenshot({ path: `${EVID}/${info.project.name}-kampagne-klar.png`, fullPage: true });

  // a direct API attempt is refused and nothing changes; reload shows the same draft
  const r = await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/start`, { headers: CSRF,
    data: { expected_version: c.version, legal_confirmed: true, accept_max_net_minor: 999999 } });
  expect([409, 501]).toContain(r.status());
  await page.reload();
  await expect(page.getByText("Kladde", { exact: true }).first()).toBeVisible();
  expect((await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns/${c.id}`)).json()).status).toBe("draft");
});

test("C11 · tælleren i startboksen: «{n} opkald» er antal kontakter, ikke opkald (DB-003)", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info, "campaigns");
  const goals = await (await page.request.get(`/api/backend/workspaces/${wsId}/goals`)).json();
  const { version, ...g } = goals;
  await page.request.put(`/api/backend/workspaces/${wsId}/goals`, { headers: CSRF, data: { ...g, callback: true, expected_version: version } });
  const c = await (await page.request.post(`/api/backend/workspaces/${wsId}/campaigns`, { headers: CSRF, data: { name: `QA-EB tæller ${info.project.name}`, purpose: "Tilbud" } })).json();
  const out = await (await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/contacts/import`, { headers: CSRF,
    data: { csv: "Mette;20304050\nOle;21222324", kind: "business", consent_source: "Tilmelding på hjemmesiden, marts 2026" } })).json();
  const camp = out.campaign;
  // 2 contacts × max_attempts (2) = up to 4 outbound calls are what the shown maximum pays for
  const maxCalls = camp.counts.by_status.pending * camp.pricing.max_attempts;
  await page.goto(`/app/kampagner/${c.id}`);
  const heading = page.locator("aside h2").first();
  await expect(heading).toBeVisible();
  await page.screenshot({ path: `${EVID}/${info.project.name}-startboks-taeller.png`, fullPage: true });
  await expect(heading).not.toHaveText(new RegExp(`^${camp.counts.by_status.pending} opkald`));
  await expect(heading).toHaveText(new RegExp(`${camp.counts.by_status.pending} kontakter|${maxCalls} opkald`));
});
