import { expect, test } from "@playwright/test";
import { freshOwner, login, SEEDED } from "../../helpers";
import { approve, ALL_WEEK, CSRF, EVID } from "./d-helpers";

/* S03 – /app/settings/integrations: «Connection directory with available, connected, limited, stale, disconnected and
 * reconnect states; booking links use BK05/BK07.» Built as the sheet /app/indstillinger?ark=integrationer. */
async function forward8000(page: import("@playwright/test").Page) {
  await page.context().route("http://localhost:8000/**", async (route) => {
    try { await route.fulfill({ response: await route.fetch({ url: route.request().url().replace("localhost:8000", "localhost:8200"), maxRedirects: 0 }) }); } catch { /* closed */ }
  });
}
const card = (page: import("@playwright/test").Page, key: string) => page.locator(`li[data-connector="${key}"]`);

test("S03 · oversigt: ikke-byggede er «Ikke tilgængelig» (aldrig grøn), forbind → «Forbundet (simuleret)», afbryd → «Ikke forbundet»", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await forward8000(page);
  await page.goto("/app/indstillinger?ark=integrationer");
  const cat = await (await page.request.get(`/api/backend/workspaces/${wsId}/integrations`)).json();
  const notImpl = (cat.items as { key: string; status: string }[]).filter((c) => c.status === "not_implemented");
  expect(notImpl.length).toBeGreaterThan(0);
  for (const c of notImpl) {
    // not-built connectors are listed under «På vej» (no card with actions) – never as connected
    if (await card(page, c.key).count()) await expect(card(page, c.key)).not.toContainText("Forbundet");
  }
  const g = card(page, "google_calendar");
  await expect(g).toContainText("Ikke forbundet");
  await g.getByRole("button", { name: "Forbind" }).click();
  await page.waitForURL(/indstillinger\?ark=integrationer/);
  await page.waitForLoadState("networkidle");
  await expect(card(page, "google_calendar")).toContainText("Forbundet (simuleret)");
  await page.screenshot({ path: `${EVID("S03")}/${info.project.name}-forbundet.png`, fullPage: true });
  await card(page, "google_calendar").getByRole("button", { name: "Afbryd" }).click();
  await card(page, "google_calendar").getByRole("button", { name: "Ja, afbryd Google Kalender" }).click();
  await expect(card(page, "google_calendar")).toContainText("Ikke forbundet");
  const after = (await (await page.request.get(`/api/backend/workspaces/${wsId}/integrations`)).json()).items.find((c: { key: string }) => c.key === "google_calendar");
  expect(after.status).toBe("not_connected");
});

async function calendarDown(page: import("@playwright/test").Page, info: import("@playwright/test").TestInfo) {
  const { wsId } = await freshOwner(page, info);
  await forward8000(page);
  await approve(page.request, wsId, "opening_hours", "Åbningstider", { weekly: ALL_WEEK });
  const typ = await (await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } })).json();
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-e2d-s03-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await page.goto(r.authorize_url);
  await expect(page).toHaveURL(/integrationer/);
  await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=true`, { headers: CSRF });
  return { wsId, typeId: typ.id as string };
}
const gcal = async (page: import("@playwright/test").Page, wsId: string) =>
  (await (await page.request.get(`/api/backend/workspaces/${wsId}/integrations`)).json()).items.find((c: { key: string }) => c.key === "google_calendar");

test("S03 · kalenderen kan ikke læses ved opslag af ledige tider: forbindelsen står derefter som fejl (ikke «Forbundet · sidst bekræftet»)", async ({ page }, info) => {
  const { wsId, typeId } = await calendarDown(page, info);
  try {
    // the owner's «Book for en kunde» and the widget both read free times this way (GET, no booking made)
    const sl = await page.request.get(`/api/backend/workspaces/${wsId}/bookings/slots?type_id=${typeId}`);
    expect(sl.ok()).toBeTruthy();
    expect((await sl.json()).items.length).toBeGreaterThan(0); // fail-open: times from opening hours
    await page.goto("/app/indstillinger?ark=integrationer");
    await page.screenshot({ path: `${EVID("S03")}/${info.project.name}-nede-men-forbundet.png`, fullPage: true });
    // credentials.mark_error() runs in connected_busy(), but the GET never commits (db.close → rollback)
    expect((await gcal(page, wsId)).status).toBe("error");
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=false`, { headers: CSRF });
  }
});

test("S03 · en kalender i fejl tilbyder «Forbind igen» (reconnect), ikke kun «Test» og «Afbryd»", async ({ page }, info) => {
  const { wsId, typeId } = await calendarDown(page, info);
  try {
    const sl = (await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/slots?type_id=${typeId}`)).json()).items;
    // a booking (POST, commits) records the outage on the connection
    expect((await page.request.post(`/api/backend/workspaces/${wsId}/bookings`, { headers: CSRF, data: { type_id: typeId, start: sl[0].start, name: "Henrik Villumsen", phone: "+45 20 30 40 50", email: null, note: "" } })).ok()).toBeTruthy();
    expect((await gcal(page, wsId)).status).toBe("error");
    await page.goto("/app/indstillinger?ark=integrationer");
    const g = card(page, "google_calendar");
    await expect(g).toContainText("Fejl");
    await page.screenshot({ path: `${EVID("S03")}/${info.project.name}-fejl.png`, fullPage: true });
    await expect(g.getByRole("button", { name: /Forbind igen|Genforbind/ })).toBeVisible();
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=false`, { headers: CSRF });
  }
});

test("S03 · kravets adresse /app/settings/integrations leder til oversigten (som /app/settings/integrationer gør)", async ({ page }, info) => {
  await freshOwner(page, info);
  const r = await page.request.get("/app/settings/integrations", { maxRedirects: 0 });
  test.info().annotations.push({ type: "status", description: String(r.status()) });
  expect([301, 307, 308]).toContain(r.status());
});

test("S03 · læser blokeres i UI og kan ikke forbinde via API'et", async ({ page }) => {
  await login(page, SEEDED.reader);
  await page.goto("/app/indstillinger?ark=integrationer");
  await expect(page.locator("li[data-connector]")).toHaveCount(0);
  const wss = await (await page.request.get("/api/backend/workspaces")).json();
  const wsId = ((wss.items ?? wss)[0]).id as string;
  const r = await page.request.post(`/api/backend/workspaces/${wsId}/integrations/webhook/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-e2d-s03r-${Date.now()}` }, data: { config: { url: "https://hooks.example.com/x" }, secrets: {} } });
  expect(r.status()).toBe(403);
});
