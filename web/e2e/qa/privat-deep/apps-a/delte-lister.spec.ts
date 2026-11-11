import { expect, test } from "@playwright/test";
import { appSuite } from "./suite";
import { backendTrace, CSRF, direct, guard, persona, sayInChat, shot, sql, waitIdle } from "./apps-a-helpers";

/** PC-APP-DELTE-LISTER-01..05. Delte lister is a default app (on at sign-up, setup done) and keeps its things in the
 *  lists themselves – no app endpoint, no «Slet data». API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "delte-lister", sc: "PC-APP-DELTE-LISTER", plan: false,
  say: "", shows: /./, read: "/privat/tasks", holds: () => true, dbCount: () => 1,
  skip: { "03": "eget flow herunder", "04": "eget flow herunder", "05": "eget flow herunder" },
});

test.describe("delte-lister – del og afinstallér", () => {
  guard();
  test("PC-APP-DELTE-LISTER-03 «Del listen med Anna» på listen → link + tekst fra eget nummer; Dialogbot sender intet", async ({ page }, info) => {
    const trace = backendTrace(page);
    const { ws } = await persona(page, info, "dl-03", "trial");
    await sayInChat(page, "Lav en indkøbsliste med mælk, æg og rugbrød");
    const tasks = (await (await page.request.get("/api/backend/privat/tasks")).json()) as { id: string; title: string; kind: string }[];
    const list = tasks.find((t) => t.kind === "list")!;
    const outboxBefore = Number(sql(`select count(*) from outbox_events where event_type ilike '%sms%'`)[0]);
    const r = await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: "Del listen med Anna", about_task_id: list.id } });
    const msgs = (await r.json()).messages as { kind: string; text: string }[];
    expect(msgs.map((m) => m.kind)).toContain("share_proposal");
    expect(msgs.find((m) => m.kind === "share_proposal")!.text).toContain(list.title);
    const share = await page.request.post(`/api/backend/privat/tasks/${list.id}/share`, { headers: CSRF, data: { mode: "group", role: "editor" } });
    expect(share.status()).toBe(200);
    const s = await share.json();
    expect(s.suggested_text).toContain(s.short_url.split("://")[1]);
    expect(s.suggested_text.length).toBeLessThanOrEqual(160);
    expect(sql(`select share_mode from private_tasks where id='${list.id}'`)[0]).toBe("group");
    expect(Number(sql(`select count(*) from outbox_events where event_type ilike '%sms%'`)[0])).toBe(outboxBefore);
    await page.goto(`/privat/opgaver/${list.id}`);
    await waitIdle(page);
    await shot(page, info, "PC-APP-DELTE-LISTER-03", "list-shared");
    expect(ws).toBeTruthy();
    trace.assertReal();
  });

  test("PC-APP-DELTE-LISTER-05 slå fra → deling på pause, listen gemt, ingen «Slet data» → slå til igen", async ({ page }, info) => {
    const trace = backendTrace(page);
    await persona(page, info, "dl-05", "trial");
    await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: "Lav en indkøbsliste med mælk og rugbrød" } });
    const list = ((await (await page.request.get("/api/backend/privat/tasks")).json()) as { id: string; kind: string }[]).find((t) => t.kind === "list")!;
    await page.request.post(`/api/backend/privat/tasks/${list.id}/share`, { headers: CSRF, data: { mode: "group", role: "editor" } });
    await page.goto("/privat/apps/delte-lister");
    await waitIdle(page);
    await page.locator("[data-testid=disable-app]:visible").first().click();
    await expect(page.getByText(/Delingen sættes på pause/)).toBeVisible();
    await shot(page, info, "PC-APP-DELTE-LISTER-05", "disable-sheet");
    await page.getByTestId("disable-confirm").click();
    await expect(page).toHaveURL(/\/privat\/apps$/, { timeout: 15_000 });
    expect((await direct(page, `/privat/tasks/${list.id}`)).status).toBe(200);
    const del = await page.request.delete("/api/backend/privat/addons/delte-lister/data", { headers: CSRF });
    expect([del.status(), (await del.json()).code]).toEqual([409, "not_deletable"]);
    await page.goto("/privat/apps/delte-lister");
    await waitIdle(page);
    await expect(page.getByTestId("app-kept")).toBeVisible();
    await expect(page.getByRole("button", { name: "Slet data" })).toHaveCount(0);
    await page.getByTestId("enable-again").click();
    await page.getByTestId("enable-confirm").click();
    await expect.poll(async () => (await direct<{ key: string; enabled: boolean }[]>(page, "/privat/addons")).body.find((a) => a.key === "delte-lister")?.enabled).toBe(true);
    trace.assertReal();
  });
});
