import { expect, test } from "@playwright/test";
import { closeAll, EVID, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W06 – callback confirmation: «Verified number, chosen time, reason, amend/cancel flow and resulting states.» */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

async function request(chat: import("@playwright/test").FrameLocator, windowIndex: number) {
  await chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" }).click();
  const form = chat.locator("form.contact");
  await form.getByLabel("Navn").fill("Henrik Villumsen");
  await form.getByLabel("Telefon").fill("+45 20 30 40 50");
  const sel = form.getByLabel("Hvornår må vi ringe?");
  await expect(sel.locator("option")).not.toHaveCount(1);
  await sel.selectOption({ index: windowIndex });
  const label = (await sel.locator("option:checked").textContent())!;
  await form.getByLabel("Virksomheden må kontakte mig om min henvendelse.").check();
  await form.getByRole("button", { name: "Send" }).click();
  return label;
}

test("W06 · bekræftelsen nævner det valgte tidsrum (ikke «hurtigst muligt», når kunden valgte et tidsrum)", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  const label = await request(chat, 2);
  const ok = chat.locator("li.msg.system-ok").last();
  await expect(ok).toContainText("Tak, Henrik Villumsen!");
  await v.screenshot({ path: `${EVID("W06")}/${info.project.name}-bekraeftelse.png` });
  await expect(ok).toContainText(label.replace(/\s*\(.*\)$/, "").trim().toLowerCase().split(" ")[0], { ignoreCase: true });
  await expect(ok).not.toContainText("hurtigst muligt");
  await close();
});

test("W06 · kunden ændrer tidsrummet (ny besked efter reload): opgaven følger det nye tidsrum, ikke det gamle", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  const first = await request(chat, 2);
  await expect(chat.getByText("Tak, Henrik Villumsen!")).toBeVisible();
  // the visitor changes their mind: reload the page (same conversation via sessionStorage), choose the other window
  await v.reload();
  await v.getByRole("button", { name: "Åbn chat" }).click();
  const second = await request(chat, 3);
  expect(second).not.toBe(first);
  await expect(chat.getByText("Tak, Henrik Villumsen!")).toBeVisible();
  const leads = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/leads`)).json()).items;
  expect(leads.length).toBe(1);
  const tasks = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/tasks`)).json()).items as { title: string; due_at: string }[];
  await v.screenshot({ path: `${EVID("W06")}/${info.project.name}-aendret.png` });
  // lead.callback_from moves to the new window (leads/service.py:191) – the open task must too
  expect(new Date(tasks[0].due_at).getTime()).toBe(new Date(leads[0].callback_from).getTime());
  expect(tasks.map((t) => t.title)).toEqual([`Ring Henrik Villumsen op – ${second}`]);
  await close();
});

test("W06 · ikke bygget: bekræftet nummer (kode) og «Aflys opringning» i widgetten", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { chat, close } = await visitor(browser, page);
  await request(chat, 2);
  await expect(chat.getByText("Tak, Henrik Villumsen!")).toBeVisible();
  // documents the gap for the lead; fails until a verify/cancel flow exists
  await expect(chat.getByRole("button", { name: /Aflys|Annullér opringning|Ret/ })).toBeVisible({ timeout: 3000 });
  await close();
});
