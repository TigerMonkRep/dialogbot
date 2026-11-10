import { expect, test } from "@playwright/test";
import { freshOwner, shot } from "../../helpers";

/* E02 (integrations-qa, bølge 2 / M2): «Owner conversation email – Concise summary, next action and secure deep link
 * into the correct workspace.» Den mail, der findes, er «Ny henvendelse» (email.new_lead). Linket er
 * /app/leads/<id> uden arbejdsrum – den aktive workspace-cookie afgør, hvor siden slår op. Test: ejer med to
 * arbejdsrum, aktiv = B, henvendelse i A → linket fra mailen skal vise henvendelsen (eller skifte til A). */

const CSRF = { "x-requested-with": "dialogbot" };

test("E02 · mail-link til ny henvendelse lander i det rigtige arbejdsrum", async ({ page }, info) => {
  const { wsId: wsA } = await freshOwner(page, info);
  const name = `Mette E02 ${Date.now()}`;
  // a customer books online (bookings/service.py → leads._notify_new_lead → email.new_lead to owner/admin)
  const api = (path: string, data?: unknown, method = "post") => (page.request as any)[method](`/api/backend/workspaces/${wsA}${path}`, { headers: CSRF, data });
  const it = await (await api("/knowledge/items", { kind: "opening_hours", title: "Åbningstider", content: { weekly: [{ days: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], open: "08:00", close: "20:00" }] } })).json();
  expect((await api(`/knowledge/versions/${it.open_draft.id}/submit`)).ok()).toBeTruthy();
  expect((await api(`/knowledge/versions/${it.open_draft.id}/approve`)).ok()).toBeTruthy();
  const type = await (await api("/bookings/types", { name: "Besigtigelse", duration_minutes: 60 })).json();
  const st = await (await page.request.get(`/api/backend/workspaces/${wsA}/bookings/settings`, { headers: CSRF })).json();
  expect((await api("/bookings/settings", { expected_version: st.version, enabled: true, lead_time_hours: 0, horizon_days: 7, buffer_minutes: 0 }, "put")).ok()).toBeTruthy();
  const slot = (await (await page.request.get(`/api/backend/workspaces/${wsA}/bookings/slots?type_id=${type.id}`, { headers: CSRF })).json()).items[0];
  const b = await api("/bookings", { type_id: type.id, start: slot.start, name, phone: "+4520304050", note: "Tilbud på slibning af 65 m² stuegulv" });
  expect(b.status(), await b.text()).toBe(201);
  const leadId = (await b.json()).lead_id as string;
  expect(leadId).toBeTruthy();

  // the mail arrives (simulated mailbox) with summary, an action and a link
  let mail: { subject: string; body_text: string } | undefined;
  await expect.poll(async () => {
    const r = await page.request.get("/api/backend/dev/mailbox");
    const items = ((await r.json()) as { items: { subject: string; body_text: string }[] }).items;
    mail = items.find((m) => m.body_text.includes(leadId));
    return Boolean(mail);
  }, { timeout: 30_000 }).toBeTruthy();
  const link = mail!.body_text.match(/https?:\/\/\S+\/app\/leads\/[\w-]+\S*/)![0];
  info.attach("e02-mail.txt", { body: `${mail!.subject}\n\n${mail!.body_text}`, contentType: "text/plain" });
  expect(mail!.body_text).toContain(name);

  // second workspace becomes the active one (as after using the switcher)
  const wsB = await (await page.request.post("/api/backend/workspaces", { headers: CSRF, data: { name: `E02 B ${Date.now()}`, product_intent: "reception" } })).json();
  expect((await page.request.post("/api/auth/workspace", { headers: CSRF, data: { workspace_id: wsB.id } })).ok()).toBeTruthy();

  await page.goto(new URL(link).pathname + new URL(link).search);
  await shot(page, info, "e02-deeplink-aktivt-andet-arbejdsrum");
  await expect(page.getByRole("heading", { name })).toBeVisible();
});
