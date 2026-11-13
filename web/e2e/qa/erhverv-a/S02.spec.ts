import { expect, test, type Browser, type Page, type TestInfo } from "@playwright/test";
import { DEMO_PASSWORD, freshOwner, latestMailLink, login, SEEDED, uniqueEmail } from "../../helpers";

/* QA S02 (e2e-erhverv A): /app/settings/team (→ /app/konto) – members, invites, roles, resend/revoke, remove with
 * confirmation. Source: web/src/app/app/(admin)/konto/team.tsx, app/modules/workspaces/service.py. */
const EVID = "../qa/evidence/S02";
const CSRF = { "x-requested-with": "dialogbot" };

/** Invite through the API as the page's owner and accept in a separate browser context. Returns the member email. */
async function addMember(page: Page, browser: Browser, info: TestInfo, wsId: string, role: string, tag: string) {
  const email = uniqueEmail(tag, info);
  expect((await page.request.post(`/api/backend/workspaces/${wsId}/invitations`, { headers: CSRF, data: { email, role } })).status()).toBe(201);
  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL });
  const r = ctx.request;
  expect((await r.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: `QA ${tag}`, signup_intent: "reception" } })).status()).toBe(201);
  expect((await r.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  const token = (await latestMailLink(r, /\/invite\/[\w-]+/)).split("/invite/")[1];
  expect((await r.post("/api/backend/invitations/accept", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  await ctx.close();
  return email;
}
const roleOf = async (page: Page, wsId: string, email: string) =>
  ((await (await page.request.get(`/api/backend/workspaces/${wsId}/members`)).json()) as { email: string; role: string }[]).find((m) => m.email === email)?.role;

test("S02 · «Kan ændre» betyder det samme ved invitation og ved rolleskift", async ({ page, browser }, info) => {
  // F-EA-04-S02: safer default 13/11 – «Kan ændre» is staff both ways (least privilege); Fürster may still choose admin.
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/settings/team");
  await expect(page).toHaveURL(/\/app\/konto$/);
  // Invite with «Kan ændre» through the UI …
  const invited = uniqueEmail("kanaendre", info);
  await page.getByLabel("Invitér med e-mail").fill(invited);
  await page.getByLabel("Må", { exact: true }).selectOption({ label: "Kan ændre" });
  await page.getByRole("button", { name: "Invitér", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Invitationen er sendt." })).toBeVisible();
  await expect(page.getByText(invited)).toBeVisible();
  const inv = ((await (await page.request.get(`/api/backend/workspaces/${wsId}/invitations`)).json()) as { email: string; role: string }[]).find((i) => i.email === invited)!;
  // … and turn a «Kan se» member into «Kan ændre» through the UI.
  const reader = await addMember(page, browser, info, wsId, "reader", "laeser");
  await page.reload();
  const sel = page.getByLabel(/^Rolle for QA laeser/).filter({ visible: true });
  await sel.selectOption({ label: "Kan ændre" });
  await expect.poll(() => roleOf(page, wsId, reader)).not.toBe("reader");
  await page.screenshot({ path: `${EVID}/${info.project.name}-roller.png`, fullPage: true });
  const changed = await roleOf(page, wsId, reader);
  info.annotations.push({ type: "roles", description: `invite «Kan ændre» → ${inv.role}; change to «Kan ændre» → ${changed}` });
  // Same label must give the same permissions (staff cannot invite or approve knowledge; admin can).
  expect(changed, "«Kan ændre» via rolleskift giver en anden backend-rolle end «Kan ændre» via invitation").toBe(inv.role);
  expect(inv.role).toBe("staff");
});

test("S02 · fjern medlem og tilbagekald invitation kræver bekræftelse; «Annullér» ændrer intet; reload viser sandheden", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const member = await addMember(page, browser, info, wsId, "staff", "fjern");
  const pendingEmail = uniqueEmail("afventer", info);
  await page.request.post(`/api/backend/workspaces/${wsId}/invitations`, { headers: CSRF, data: { email: pendingEmail, role: "reader" } });
  await page.goto("/app/konto");
  const row = page.locator("tr", { hasText: member });
  // dismiss → still a member
  page.once("dialog", (d) => { expect(d.message()).toContain("Fjern QA fjern"); void d.dismiss(); });
  await row.getByRole("button", { name: "Fjern" }).click();
  await page.waitForTimeout(500);
  expect(await roleOf(page, wsId, member)).toBe("staff");
  // accept → removed, survives reload
  page.once("dialog", (d) => void d.accept());
  await row.getByRole("button", { name: "Fjern" }).click();
  await expect.poll(() => roleOf(page, wsId, member)).toBeUndefined();
  await page.reload();
  await expect(page.locator("tr", { hasText: member })).toHaveCount(0);
  // resend keeps it pending; revoke with confirmation removes it from the list
  const invRow = page.locator("li", { hasText: pendingEmail });
  await invRow.getByRole("button", { name: "Send igen" }).click();
  await expect(invRow).toBeVisible();
  page.once("dialog", (d) => void d.dismiss());
  await invRow.getByRole("button", { name: "Tilbagekald" }).click();
  await page.waitForTimeout(500);
  await expect(invRow).toBeVisible();
  page.once("dialog", (d) => { expect(d.message()).toContain("Tilbagekald invitationen"); void d.accept(); });
  await invRow.getByRole("button", { name: "Tilbagekald" }).click();
  await expect(page.locator("li", { hasText: pendingEmail })).toHaveCount(0);
  const invs = (await (await page.request.get(`/api/backend/workspaces/${wsId}/invitations`)).json()) as { email: string; status: string }[];
  expect(invs.find((i) => i.email === pendingEmail)?.status).toBe("revoked");
  // the last owner has no remove/leave button
  await expect(page.locator("tr", { hasText: "(dig)" }).getByRole("button")).toHaveCount(0);
  await page.screenshot({ path: `${EVID}/${info.project.name}-efter-fjern.png`, fullPage: true });
});

test("S02 · læser ser medlemmer, men ingen invitationsformular eller rollevalg; server afviser alligevel", async ({ page }, info) => {
  await login(page, SEEDED.reader);
  await page.goto("/app/konto");
  await expect(page.getByRole("heading", { name: "Hvem må se og ændre" })).toBeVisible();
  await expect(page.getByText("Kun ejere og administratorer kan invitere og ændre roller.")).toBeVisible();
  await expect(page.getByLabel("Invitér med e-mail")).toHaveCount(0);
  await expect(page.locator("select[aria-label^='Rolle for']")).toHaveCount(0);
  const ws = ((await (await page.request.get("/api/backend/workspaces")).json()) as { id: string }[])[0];
  const r = await page.request.post(`/api/backend/workspaces/${ws.id}/invitations`, { headers: CSRF, data: { email: uniqueEmail("x", info), role: "reader" } });
  expect(r.status()).toBe(403);
  expect(await page.locator("body").innerText()).not.toMatch(/staging/i);
  await page.screenshot({ path: `${EVID}/${info.project.name}-laeser.png`, fullPage: true });
});
