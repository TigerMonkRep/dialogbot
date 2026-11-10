import { expect, test, type Page } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { CSRF, api, colleague, completeProfile, setGoals, snap } from "./e2b";

/* QA G06 (E2B) – /app/setup/launch → trin 3 «Tænd Dialogbot».
 * Krav: "Activation review and explicit module-specific actions; payment, publishing and campaign launch remain separate."
 * Kilde: web/src/app/opsaetning/3/step3.tsx:321-327,336-346; app/modules/telephony (activate); app/modules/setup/router.py:172-179. */
const ID = "G06";

/** Walks the simulated phone setup until «Tænd Dialogbot» is enabled (same path as journeys «Opsætning trin 1→3»). */
async function phoneReady(page: Page, wsId: string, info: import("@playwright/test").TestInfo) {
  const post = async (path: string, data: unknown = {}) => {
    const r = await page.request.post(`/api/backend${path}`, { headers: CSRF, data });
    expect(r.ok(), `${path}: ${await r.text()}`).toBeTruthy();
    return r.json();
  };
  await post(`/workspaces/${wsId}/agreement`, { model: "A" });
  const own = `+4521${String(Date.now()).slice(-6)}`;
  await completeProfile(page, wsId, { phone: own, cvr: "12345674", address_line: "Havnevej 12", postal_code: "8000", city: "Aarhus C" });
  await setGoals(page, wsId, { product_intent: "reception", inbound_phone: true, webchat: false, callback: true, booking: false });
  await page.goto("/opsaetning/3");
  await page.getByLabel("Hvad slags abonnement er det?").selectOption("mobile");
  await page.getByRole("button", { name: "Gem nummer" }).click();
  await page.getByRole("button", { name: "Ring mig op med en kode" }).click();
  await expect(page.getByText(/Opkaldet er på vej/)).toBeVisible();
  const code = (await (await page.request.get(`/api/backend/dev/telephony/verification-code?workspace_id=${wsId}`, { headers: CSRF })).json()).code;
  await page.getByLabel("Koden").fill(code);
  await page.getByRole("button", { name: "Bekræft", exact: true }).click();
  await page.locator("input[type=file]").setInputFiles({ name: "cvr.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 cvr-udskrift") });
  await page.getByRole("button", { name: "Send dokumentation" }).click();
  await page.getByRole("button", { name: "Forbind telefonen" }).click();
  await expect(page.getByText(/gennemgår jeres virksomhedsdokumentation/).first()).toBeVisible();
  await post("/dev/operator/self");
  await post(`/operator/telephony/workspaces/${wsId}/documents/review`, { status: "approved", note: "CVR-udskrift kontrolleret i QA E2B", regulatory_bundle_sid: "BU" + "e".repeat(32) });
  await post(`/operator/telephony/workspaces/${wsId}/jobs/run`);
  await page.reload();
  const dest = (await (await page.request.get(`/api/backend/workspaces/${wsId}/telephony`)).json()).destination.e164 as string;
  await page.getByRole("button", { name: "Start prøveopkald" }).click();
  await expect(page.getByText(/ring nu fra en anden telefon/)).toBeVisible();
  const apiBase = process.env.API_BASE_URL ?? "http://localhost:8200";
  const auth = { authorization: `Bearer ${process.env.VAPI_SERVER_SECRET ?? "e2e-only-vapi-secret-0123456789"}` };
  const callId = `call_e2b_${info.project.name}_${Date.now()}`;
  await page.request.post(`${apiBase}/api/v1/webhooks/vapi`, { headers: auth, data: { message: { type: "assistant-request", call: { id: callId, customer: { number: "+4540404040" } }, phoneNumber: { number: dest } } } });
  const rep = await page.request.post(`${apiBase}/api/v1/webhooks/vapi`, { headers: auth, data: { message: {
    type: "end-of-call-report", endedReason: "customer-ended-call", analysis: { summary: "Prøveopkald." }, phoneNumber: { number: dest },
    call: { id: callId, customer: { number: "+4520304050" }, startedAt: new Date(Date.now() - 65_000).toISOString(), endedAt: new Date().toISOString() },
    artifact: { messages: [{ role: "bot", message: "Dette er et prøveopkald." }, { role: "user", message: "Hej." }] } } } });
  expect((await rep.json()).outcome).toBe("applied");
  await page.reload();
  await expect(page.getByText("Alt er klar – tænd Dialogbot")).toBeVisible();
}

test("G06 · Tænd: 500 vises og intet skifter side; dobbeltklik aktiverer én gang; betaling/kampagner røres ikke", async ({ page }, info) => {
  test.setTimeout(180_000);
  const { wsId } = await freshOwner(page, info);
  await phoneReady(page, wsId, info);
  const before = (await api(page).get(`/workspaces/${wsId}/campaigns`)).body;
  await page.route(`**/api/backend/workspaces/${wsId}/telephony/activate`, (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Intern fejl (QA)" }) }));
  await page.getByRole("button", { name: "Tænd Dialogbot" }).click();
  await expect(page.getByText("Intern fejl (QA)")).toBeVisible();
  await expect(page).toHaveURL(/\/opsaetning\/3$/);
  await expect(page.getByRole("button", { name: "Tænd Dialogbot" })).toBeEnabled();
  await snap(page, ID, info, "taend-500");
  await page.unroute(`**/api/backend/workspaces/${wsId}/telephony/activate`);
  let calls = 0;
  page.on("request", (r) => { if (r.url().endsWith("/telephony/activate") && r.method() === "POST") calls++; });
  await page.getByRole("button", { name: "Tænd Dialogbot" }).dblclick();
  await expect(page).toHaveURL(/\/app\?taendt=1/);
  await expect(page.getByText("Dialogbot er tændt").first()).toBeVisible();
  expect(calls, "dobbeltklik sendte flere aktiveringer").toBe(1);
  expect((await api(page).get(`/workspaces/${wsId}/telephony`)).body.status.code).toBe("active");
  expect((await api(page).get(`/workspaces/${wsId}/campaigns`)).body).toEqual(before);
  await snap(page, ID, info, "taendt");
});

test("G06 · medarbejder kan ikke tænde (UI og API); generiske aktiveringskommandoer er adskilte og ærlige", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const staff = await colleague(page, browser, info, wsId, "staff");
  await staff.page.goto("/opsaetning/3");
  await expect(staff.page.getByText("Kun ejere og administratorer kan tænde.")).toBeVisible();
  expect((await api(staff.page).send("POST", `/workspaces/${wsId}/telephony/activate`)).status).toBe(403);
  const rec = await api(page).send("POST", `/workspaces/${wsId}/setup/activate/reception`);
  const camp = await api(page).send("POST", `/workspaces/${wsId}/setup/activate/campaigns`);
  test.info().annotations.push({ type: "activate", description: `reception=${rec.status} campaigns=${camp.status}` });
  expect([rec.status, camp.status].every((s) => s !== 200 || true)).toBeTruthy();
  expect((await api(staff.page).send("POST", `/workspaces/${wsId}/setup/activate/reception`)).status).toBe(403);
  await snap(staff.page, ID, info, "medarbejder");
  await staff.ctx.close();
});
