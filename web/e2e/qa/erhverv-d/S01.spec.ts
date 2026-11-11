import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";
import { CSRF, EVID } from "./d-helpers";

/* S01 – /app/settings/business: «Business profile, editable categories, address, hours, primary language and time
 * zone.» The route is a permanent redirect to /opsaetning/1 (trin 1), which autosaves. */
test("S01 · adresse, åbningstider og primært sprog rettes, gemmes automatisk og står der efter reload", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/settings/business");
  await expect(page).toHaveURL(/\/opsaetning\/1$/);
  await page.getByText("CVR og adresse (valgfrit)").click(); // opens the <details> with CVR/address
  await page.getByLabel("Adresse", { exact: true }).fill("Søndergade 12");
  await page.getByLabel("Postnummer", { exact: true }).fill("8000");
  await page.getByLabel("By", { exact: true }).fill("Aarhus C");
  await page.getByLabel("Åbningstider").fill("Man–fre 07–16; lør 09–12");
  await page.getByLabel("Sprog over for jeres kunder").selectOption("en");
  await expect.poll(async () => {
    const p = await (await page.request.get(`/api/backend/workspaces/${wsId}/profile`)).json();
    return [p.address_line, p.postal_code, p.city].join("|");
  }, { timeout: 15_000 }).toBe("Søndergade 12|8000|Aarhus C");
  await expect.poll(async () => (await (await page.request.get(`/api/backend/workspaces/${wsId}/languages`)).json()).default_conversation_language, { timeout: 15_000 }).toBe("en");
  await expect.poll(async () => {
    const items = (await (await page.request.get(`/api/backend/workspaces/${wsId}/knowledge/items`)).json()).items as { kind: string }[];
    return items.some((i) => i.kind === "opening_hours");
  }, { timeout: 15_000 }).toBeTruthy();
  await page.reload();
  await expect(page.getByLabel("Åbningstider")).toHaveValue(/07.?16/);
  await expect(page.getByLabel("Sprog over for jeres kunder")).toHaveValue("en");
  await page.screenshot({ path: `${EVID("S01")}/${info.project.name}-virksomhed.png`, fullPage: true });
  const audit = (await (await page.request.get(`/api/backend/workspaces/${wsId}/audit?limit=50`)).json()).items as { action: string }[];
  expect(audit.map((a) => a.action)).toContain("profile.updated");
});

test("S01 · kategorier og tidszone kan ses og rettes på virksomhedssiden", async ({ page }, info) => {
  test.fail(true, "F-E2D-12-S01: S2 new – Virksomhedssiden (/app/settings/business → /opsaetning/1) viser hverken kategorier eller …");
  const { wsId } = await freshOwner(page, info);
  // a category exists (as trin 1 derives it), the page must show it and let the owner change it
  await page.request.post(`/api/backend/workspaces/${wsId}/categories`, { headers: CSRF, data: { label: "Gulvafslibning", slug: null, is_primary: true } });
  await page.goto("/app/settings/business");
  await page.screenshot({ path: `${EVID("S01")}/${info.project.name}-kategori-tidszone.png`, fullPage: true });
  await expect(page.getByText("Gulvafslibning")).toBeVisible({ timeout: 5_000 }); // known: fail fast
  await expect(page.getByLabel(/Tidszone/i)).toBeVisible();
});

test("S01 · læser kan se, men ikke rette virksomhedsprofilen (felter låst, API 403)", async ({ page }) => {
  await login(page, SEEDED.reader);
  await page.goto("/app/settings/business");
  await expect(page.getByLabel("Navn (som den siger det)")).toBeDisabled();
  const wss = await (await page.request.get("/api/backend/workspaces")).json();
  const wsId = ((wss.items ?? wss)[0]).id as string;
  const p = await (await page.request.get(`/api/backend/workspaces/${wsId}/profile`)).json();
  const r = await page.request.put(`/api/backend/workspaces/${wsId}/profile`, { headers: CSRF, data: { ...p, legal_name: "Hacket", expected_version: p.version } });
  expect(r.status()).toBe(403);
});
