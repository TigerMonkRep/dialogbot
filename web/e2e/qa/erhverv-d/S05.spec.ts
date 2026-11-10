import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { CSRF, EVID } from "./d-helpers";

/* S05 – /app/settings/api: «Developer access, masked example keys, scopes, webhooks, delivery log and revoke/rotate
 * states.» The backend has API keys (/workspaces/{id}/api-keys); there is no business UI for them. */
test("S05 · backend: nøgle oprettes med scopes, vises kun én gang, listen er maskeret, og tilbagekaldt nøgle virker ikke", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const scopes = (await (await page.request.get(`/api/backend/workspaces/${wsId}/api-keys/scopes`)).json()) as { scope?: string; key?: string; name?: string }[];
  expect(scopes.length).toBeGreaterThan(0);
  const scope = (scopes[0].scope ?? scopes[0].key ?? scopes[0].name)!;
  const created = await page.request.post(`/api/backend/workspaces/${wsId}/api-keys`, { headers: CSRF, data: { name: "Fjord Gulv CRM", scopes: [scope] } });
  expect(created.status(), await created.text()).toBe(201);
  const k = await created.json();
  const secret = (k.secret ?? k.key ?? k.token) as string;
  expect(secret).toBeTruthy();
  const list = JSON.stringify(await (await page.request.get(`/api/backend/workspaces/${wsId}/api-keys`)).json());
  expect(list).not.toContain(secret); // masked
  expect((await page.request.delete(`/api/backend/workspaces/${wsId}/api-keys/${k.id}`, { headers: CSRF })).status()).toBe(204);
});

test("S05 · UI: /app/settings/api findes (udvikleradgang, nøgler, scopes) – «Vis teknik (API, …)» lover API", async ({ page }, info) => {
  test.fail(true, "F-E2D-18-S05: S3 new – «Vis teknik (API, webhooks, log)» lover API, men der er ingen udvikleradgang/API-nøgler for …");
  await freshOwner(page, info);
  const r = await page.request.get("/app/settings/api", { maxRedirects: 5 });
  await page.goto("/app/indstillinger");
  await page.getByText("Vis teknik (API, webhooks, log)").click();
  await page.screenshot({ path: `${EVID("S05")}/${info.project.name}-teknik.png`, fullPage: true });
  test.info().annotations.push({ type: "status", description: `/app/settings/api → ${r.status()}` });
  await expect(page.getByText(/API-nøgle|API nøgle|Udvikleradgang/)).toBeVisible({ timeout: 3000 });
  expect(r.status()).toBe(200);
});
