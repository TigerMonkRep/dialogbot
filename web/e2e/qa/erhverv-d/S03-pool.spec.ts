import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { approve, ALL_WEEK, CSRF, SITE } from "./d-helpers";

/* S03 / F-E2D-13 (verifier, bølge 2): kalenderstatus skal registreres ved et læse-opslag (GET), men må aldrig tage en
 * ekstra forbindelse fra puljen, mens anmodningen holder sin egen (hold-and-wait). Mange samtidige ledige-tider-opslag
 * under et kalenderudfald må ikke udtømme puljen: alle opslag skal svare hurtigt, fejlen skal registreres, og andre
 * sider i appen må ikke få 500. Fejlede på 1b96c6e (40 samtidige → 27 × 500 «QueuePool limit of size 5 overflow 5
 * reached»); består på 534a8a5 (status skrives i after_transaction_end, når forbindelsen er givet tilbage).
 * Test 2 rammer den offentlige widget-rute GET /public/webchat/{key}/booking (ingen login) – den egentlige DoS-vektor. */
const N = Number(process.env.QA_POOL_N ?? 40);

test("S03 · samtidige opslag af ledige tider under kalenderudfald udtømmer ikke forbindelsespuljen", async ({ page }, info) => {
  test.setTimeout(120_000);
  const { wsId } = await freshOwner(page, info);
  await approve(page.request, wsId, "opening_hours", "Åbningstider", { weekly: ALL_WEEK });
  const typ = await (await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } })).json();
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-v2-pool-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await page.goto(r.authorize_url);
  await page.waitForLoadState("networkidle"); // integrationssidens egne kald må ikke blande sig i målingen
  await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=true`, { headers: CSRF });
  try {
    const t0 = Date.now();
    const res = await Promise.all(Array.from({ length: N }, () =>
      page.request.get(`/api/backend/workspaces/${wsId}/bookings/slots?type_id=${typ.id}`, { timeout: 90_000 }).then((x) => x.status())));
    const slotsMs = Date.now() - t0;
    const other = await page.request.get(`/api/backend/workspaces/${wsId}/integrations`);
    const status = (await other.json()).items?.find((c: { key: string }) => c.key === "google_calendar")?.status;
    info.attach("pool.json", { body: JSON.stringify({ N, res, slotsMs, integrations: other.status(), status }), contentType: "application/json" });
    expect(res.every((s) => s === 200), `slots: ${res.join(",")}`).toBe(true);
    expect(slotsMs, `${N} samtidige opslag tog ${slotsMs} ms`).toBeLessThan(10_000);
    expect(other.status()).toBe(200);
    expect(status).toBe("error");
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=false`, { headers: CSRF });
  }
});

test("S03 · samtidige offentlige widget-opslag (GET /booking) under kalenderudfald udtømmer ikke puljen", async ({ page }, info) => {
  test.setTimeout(120_000);
  const { wsId } = await freshOwner(page, info);
  await approve(page.request, wsId, "opening_hours", "Åbningstider", { weekly: ALL_WEEK });
  await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } });
  const bs = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/settings`)).json();
  expect((await page.request.put(`/api/backend/workspaces/${wsId}/bookings/settings`, { headers: CSRF, data: { expected_version: bs.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 } })).ok()).toBeTruthy();
  const wc = await (await page.request.get(`/api/backend/workspaces/${wsId}/webchat`)).json();
  const put = await page.request.put(`/api/backend/workspaces/${wsId}/webchat`, { headers: CSRF, data: { expected_version: wc.version, enabled: true, allowed_origins: [SITE], greeting: "" } });
  expect(put.ok(), await put.text()).toBeTruthy();
  const key = (await put.json()).widget_key;
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-v3-pool-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await page.goto(r.authorize_url);
  await page.waitForLoadState("networkidle"); // integrationssidens egne kald må ikke blande sig i målingen
  await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=true`, { headers: CSRF });
  const api = process.env.API_BASE_URL ?? "http://localhost:8200";
  try {
    const t0 = Date.now();
    const res = await Promise.all(Array.from({ length: N }, () =>
      page.request.get(`${api}/api/v1/public/webchat/${key}/booking`, { timeout: 90_000 }).then((x) => x.status())));
    const ms = Date.now() - t0;
    const other = await page.request.get(`/api/backend/workspaces/${wsId}/integrations`);
    const status = (await other.json()).items?.find((c: { key: string }) => c.key === "google_calendar")?.status;
    info.attach("pool-widget.json", { body: JSON.stringify({ N, res, ms, integrations: other.status(), status }), contentType: "application/json" });
    expect(res.every((s) => s === 200), `widget booking: ${res.join(",")}`).toBe(true);
    expect(ms, `${N} samtidige widget-opslag tog ${ms} ms`).toBeLessThan(10_000);
    expect(other.status()).toBe(200);
    expect(status).toBe("error");
  } finally {
    await page.request.post(`/api/backend/dev/fake-calendar/busy-down?workspace_id=${wsId}&down=false`, { headers: CSRF });
  }
});
