import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { API, CSRF, evidence, go, plusUser } from "./px-helpers";

/** PX · voice-qa på den rigtige Privat-stak (:3400 → :8400, fake Vapi). Intet ringes: alt aflæses i /__qa/calls.
 *  PC-CALL-01 (forslag ringer ikke), PC-CALL-02 (needs_phone → SMS-kode fra sms.simulated → ét opkald med snapshot),
 *  PC-CALL-03 (fire parallelle «Godkend» → ét opkald), PC-CALL-07 (mobilnummer kræver confirm_business). */

type Dial = { payload: { customer: { number: string }; metadata: Record<string, string>; assistant: { firstMessage: string; model: { messages: { content: string }[] } } } };

async function dialledFor(page: Page, taskId: string): Promise<Dial[]> {
  const all = (await (await page.request.get(`${API}/__qa/calls`)).json()).dialled as Dial[];
  return all.filter((d) => d.payload.metadata?.private_task_id === taskId);
}

async function propose(page: Page): Promise<string> {
  const r = await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: "Ring til cykelværkstedet og find en tid torsdag efter klokken tre" } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const clar = (await r.json()).messages.at(-1);
  expect(clar.kind).toBe("clarify");
  const o = await page.request.post(`/api/backend/privat/messages/${clar.id}/options/${clar.options[0].id}`, { headers: CSRF });
  const prop = (await o.json()).messages.at(-1);
  expect(prop.kind).toBe("call_proposal");
  return prop.task_id as string;
}

async function verifyPhone(page: Page, phone: string) {
  expect((await page.request.post("/api/backend/privat/phone/start", { headers: CSRF, data: { phone } })).ok()).toBeTruthy();
  const e164 = "+45" + phone.replace(/\D/g, "");
  let code = "";
  await expect.poll(() => {
    const lines = readFileSync("/home/claude/pd-api.log", "utf8").split("\n").filter((l) => l.includes("sms.simulated") && l.includes(e164));
    const m = lines.at(-1)?.match(/er (\d{6})/);
    code = m?.[1] ?? "";
    return code;
  }, { timeout: 10_000 }).not.toBe("");
  const v = await page.request.post("/api/backend/privat/phone/verify", { headers: CSRF, data: { code } });
  expect(v.ok(), await v.text()).toBeTruthy();
}

const phoneFor = () => `2${Math.floor(1000000 + Math.random() * 8999999)}`;

test("PC-CALL-01/02/03 · forslag ringer ikke; needs_phone; parallel Godkend → ét opkald i /__qa/calls", async ({ page }, info) => {
  test.setTimeout(120_000);
  // qa_privat_stack shifts Privat's clock into calling hours (Wed 10:00) when started outside 08–18, so calls are «open».
  const open = true;
  await plusUser(page, info, "call");
  const tid = await propose(page);
  expect(await dialledFor(page, tid), "PC-CALL-01: intet ringet ved forslag").toEqual([]);
  // the UI card
  await go(page, `/privat/opgaver/${tid}`);
  await expect(page.getByText(/Se forslaget og godkend|Godkend/).filter({ visible: true }).first()).toBeVisible();
  const r = await page.request.post(`/api/backend/privat/calls/${tid}/approve`, { headers: CSRF, data: { share_phone: false } });
  expect(r.status()).toBe(409);
  expect((await r.json()).code).toBe("needs_phone");
  expect(await dialledFor(page, tid)).toEqual([]);
  await verifyPhone(page, phoneFor());
  if (!open) {  // the stack runs on real time: outside 08–18 the call is only scheduled («ved næste åbningstid»)
    const closed = await page.request.post(`/api/backend/privat/calls/${tid}/approve`, { headers: CSRF, data: { share_phone: false } });
    expect(closed.status()).toBe(409);
    expect((await closed.json()).code).toBe("outside_hours");
  }
  const results = await Promise.all([0, 1, 2, 3].map((i) => page.request.post(`/api/backend/privat/calls/${tid}/approve`,
    { headers: { ...CSRF, "Idempotency-Key": `px-${i % 2}` }, data: { share_phone: false, at_next_open: !open } })));
  const codes = results.map((x) => x.status());
  const d = await dialledFor(page, tid);
  const task = await (await page.request.get(`/api/backend/privat/tasks/${tid}`)).json();
  evidence(`calls-stack-${info.project.name}.json`, { open, codes, status: task.status, events: task.events?.map((e: { text: string }) => e.text),
    dialled: d.map((x) => ({ to: x.payload.customer.number, first: x.payload.assistant.firstMessage })) });
  expect(codes.every((c) => c === 200), `svar ${codes}`).toBe(true);
  if (!open) {
    expect(d, "uden for åbningstid: intet ringet").toEqual([]);
    expect(task.status).toBe("planned");
    expect(task.events.filter((e: { text: string }) => e.text.startsWith("Du godkendte")).length, "én godkendelse").toBe(1);
    return;
  }
  expect(d.length, `PC-CALL-03: præcis ét opkald (svar: ${codes})`).toBe(1);
  expect(d[0].payload.assistant.firstMessage).toMatch(/^Hej, jeg ringer fra Dialogbot på vegne af .+\. Jeg er en digital assistent\./);
  expect(d[0].payload.assistant.model.messages[0].content).toContain("Du må IKKE");
});

test("PC-CALL-07 · et mobilnummer som «virksomhed» kræver bekræftelse; intet ringes før", async ({ page }, info) => {
  await plusUser(page, info, "call07");
  await verifyPhone(page, phoneFor());
  const r = await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: "Ring til Hans Tømrer på 20 11 22 33 og bestil en tid til at se på døren" } });
  expect(r.ok()).toBeTruthy();
  const msgs = (await r.json()).messages as { kind: string; task_id: string | null; text: string }[];
  const prop = msgs.find((m) => m.kind === "call_proposal");
  evidence(`call07-${info.project.name}.json`, msgs.map((m) => [m.kind, m.text]));
  expect(prop, "forslag oprettet").toBeTruthy();
  expect(prop!.text).toMatch(/mobilnummer/);
  const a = await page.request.post(`/api/backend/privat/calls/${prop!.task_id}/approve`, { headers: CSRF, data: { share_phone: false } });
  if (a.status() === 409 && (await a.json()).code !== "outside_hours") expect((await a.json()).code).toBe("confirm_business");
  expect(await dialledFor(page, prop!.task_id!)).toEqual([]);
});
