import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { approve, ALL_WEEK, CSRF } from "./d-helpers";

/* S03 / F-E2D-13 (verifier, bølge 2): kalenderstatus skrives nu i en EGEN transaktion (connectors/calendar.py
 * _record_status) – dvs. en ekstra forbindelse fra puljen, mens anmodningens egen forbindelse holdes. Mange samtidige
 * ledige-tider-opslag (widget på en travl hjemmeside) under et kalenderudfald må ikke udtømme puljen: alle opslag skal
 * svare hurtigt, fejlen skal registreres, og andre sider i appen må ikke få 500. Fejler på 1b96c6e (40 samtidige →
 * 500 «QueuePool limit of size 5 overflow 5 reached»), består på 9ab3081 bortset fra selve statusfejlen. */
const N = Number(process.env.QA_POOL_N ?? 40);

test("S03 · samtidige opslag af ledige tider under kalenderudfald udtømmer ikke forbindelsespuljen", async ({ page }, info) => {
  test.setTimeout(120_000);
  const { wsId } = await freshOwner(page, info);
  await approve(page.request, wsId, "opening_hours", "Åbningstider", { weekly: ALL_WEEK });
  const typ = await (await page.request.post(`/api/backend/workspaces/${wsId}/bookings/types`, { headers: CSRF, data: { name: "Besigtigelse", duration_minutes: 60 } })).json();
  const r = await (await page.request.post(`/api/backend/workspaces/${wsId}/integrations/google_calendar/connect`, { headers: { ...CSRF, "Idempotency-Key": `qa-v2-pool-${Date.now()}` }, data: { config: {}, secrets: {} } })).json();
  await page.goto(r.authorize_url);
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
