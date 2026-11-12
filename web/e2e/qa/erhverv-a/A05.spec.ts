import { expect, test } from "@playwright/test";
import { DEMO_PASSWORD, freshOwner, latestMailLink, uniqueEmail } from "../../helpers";

/* QA A05 (e2e-erhverv A): /invite/:token – existing/new user, wrong account, revoked, unknown, correct workspace.
 * Source: web/src/app/invite/[token]/page.tsx + accept.tsx, app/modules/workspaces/service.py:accept_invitation. */
const EVID = "../qa/evidence/A05";
const CSRF = { "x-requested-with": "dialogbot" };

test("A05 · ukendt link, forkert konto, log ind og acceptér, dobbeltklik, genbrug og tilbagekaldt", async ({ page, browser }, info) => {
  const owner = await freshOwner(page, info);
  const wsName = ((await (await page.request.get(`/api/backend/workspaces/${owner.wsId}`)).json()) as { name: string }).name;
  const invitee = uniqueEmail("a05", info);
  await page.request.post(`/api/backend/workspaces/${owner.wsId}/invitations`, { headers: CSRF, data: { email: invitee, role: "reader" } });
  const revokedEmail = uniqueEmail("a05rev", info);
  const rev = await (await page.request.post(`/api/backend/workspaces/${owner.wsId}/invitations`, { headers: CSRF, data: { email: revokedEmail, role: "staff" } })).json();

  // The invitee exists already (registered, not verified) – read the links from the simulated mailbox.
  const api = await browser.newContext({ baseURL: info.project.use.baseURL });
  for (const e of [invitee, revokedEmail]) {
    expect((await api.request.post("/api/backend/auth/register", { headers: CSRF, data: { email: e, password: DEMO_PASSWORD, display_name: "QA Kollega", signup_intent: "reception" } })).status()).toBe(201);
  }
  await api.request.post("/api/auth/login", { headers: CSRF, data: { email: invitee, password: DEMO_PASSWORD } });
  const link = new URL(await latestMailLink(api.request, /http\S+\/invite\/[\w-]+/)).pathname;
  await api.request.post("/api/auth/logout", { headers: CSRF });
  await api.request.post("/api/auth/login", { headers: CSRF, data: { email: revokedEmail, password: DEMO_PASSWORD } });
  const revLink = new URL(await latestMailLink(api.request, /http\S+\/invite\/[\w-]+/)).pathname;
  await api.close();
  await page.request.post(`/api/backend/workspaces/${owner.wsId}/invitations/${rev.id}/revoke`, { headers: CSRF });

  // 1. unknown token
  await page.goto("/invite/findes-ikke-1234567890");
  await expect(page.getByRole("alert").filter({ hasText: "Invitationen findes ikke" })).toBeVisible();
  // 2. revoked
  await page.goto(revLink);
  await expect(page.getByText("Tilbagekaldt")).toBeVisible();
  await expect(page.getByRole("button", { name: "Acceptér invitation" })).toHaveCount(0);
  await page.screenshot({ path: `${EVID}/${info.project.name}-tilbagekaldt.png`, fullPage: true });
  // 3. logged in as the wrong person (the owner): accepting is refused with a clear message, nothing changes
  await page.goto(link);
  await expect(page.getByRole("heading", { name: `Invitation til ${wsName}` })).toBeVisible();
  await page.getByRole("button", { name: "Acceptér invitation" }).click();
  await expect(page.getByText(/sendt til en anden e-mailadresse/)).toBeVisible();
  await page.screenshot({ path: `${EVID}/${info.project.name}-forkert-konto.png`, fullPage: true });

  // 4. a fresh browser, logged out: log in from the invite, double-click accept, land in the right workspace
  const ctx = await browser.newContext({ baseURL: info.project.use.baseURL, viewport: page.viewportSize() ?? undefined });
  await ctx.addCookies([{ name: "db_setup_later", value: "1", url: info.project.use.baseURL ?? "http://localhost:3000" }]);
  const p2 = await ctx.newPage();
  await p2.goto(link);
  await expect(p2.getByText("Afventer svar")).toBeVisible();
  await expect(p2.getByText("Læser")).toBeVisible();
  await p2.getByRole("link", { name: /Log ind og acceptér/ }).click();
  await expect(p2).toHaveURL(/\/login\?next=/);
  await p2.getByLabel("E-mail").fill(invitee);
  await p2.getByLabel("Adgangskode", { exact: true }).fill(DEMO_PASSWORD);
  await p2.getByRole("button", { name: "Log ind" }).click();
  await expect(p2).toHaveURL(new RegExp(link.replace(/[-/]/g, "\\$&") + "$"));
  const accept = p2.getByRole("button", { name: "Acceptér invitation" });
  await accept.dblclick();
  await expect(p2).toHaveURL(/\/opsaetning\/virksomhed|\/app/);
  const list = (await (await p2.request.get("/api/backend/workspaces")).json()) as { id: string; role: string }[];
  expect(list).toEqual([expect.objectContaining({ id: owner.wsId, role: "reader" })]);
  await p2.screenshot({ path: `${EVID}/${info.project.name}-accepteret.png`, fullPage: true });
  // 5. the link is single use
  await p2.goto(link);
  await expect(p2.getByText("Accepteret")).toBeVisible();
  await expect(p2.getByRole("button", { name: "Acceptér invitation" })).toHaveCount(0);
  // exactly one membership was created
  const members = (await (await page.request.get(`/api/backend/workspaces/${owner.wsId}/members`)).json()) as { email: string }[];
  expect(members.filter((m) => m.email === invitee)).toHaveLength(1);
  await ctx.close();
});
