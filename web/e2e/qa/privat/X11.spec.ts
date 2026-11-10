import { expect, test, type Page } from "@playwright/test";
import { dialled, evidence, needsPrivatStack, privatUser, QA_API, startTrial, waitIdle } from "./pq-helpers";

/** X11 (P0): «Ring for mig» ringer kun efter eksplicit godkendelse – intet opkald ved forslag, reload, afvisning; ét
 *  opkald ved dobbelt-klik på «Godkend opkald». Real Privat backend with a fake Vapi (tests/qa/qa_privat_stack.py):
 *  /__qa/calls lists everything that would have been dialled. DB/outbox level: tests/qa/test_qa_privat_x11.py. */

test.beforeEach(async ({ request }) => {
  test.skip(!(await needsPrivatStack(request)), "kræver tests/qa/qa_privat_stack.py på :8100 og next på BASE_URL med API_BASE_URL=:8100");
});

const chat = (page: Page) => page.getByRole("region", { name: "Samtale" });

async function say(page: Page, text: string) {
  const input = page.locator("#privat-ask-day:visible, #privat-ask:visible").first();
  await input.fill(text);
  await input.press("Enter");
  await waitIdle(page);
}

async function proposeCall(page: Page) {
  await page.goto("/privat/samtale");
  await waitIdle(page);
  await say(page, "Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15");
  const ask = chat(page).getByTestId("location-ask").last();
  if (await ask.isVisible().catch(() => false)) {
    await ask.getByRole("button", { name: "Skriv by eller postnummer" }).click();
    await ask.getByLabel("By eller postnummer").fill("8000");
    await ask.getByRole("button", { name: "Gem" }).click();
    await waitIdle(page);
  }
  await chat(page).getByTestId("business-results").last().getByRole("button").first().click();
  await waitIdle(page);
  await expect(chat(page).getByRole("heading", { name: /^Skal jeg ringe til / }).last()).toBeVisible();
}

const mine = async (page: Page, ids: Set<string>) => (await dialled(page.request)).filter((d) => ids.has(d.payload.metadata.private_task_id));

test("forslag, reload og «Afvis» ringer aldrig; dobbelt-klik på «Godkend opkald» ringer én gang", async ({ page }, info) => {
  const { email } = await privatUser(page, info, "x11");
  await startTrial(page);
  expect((await page.request.post(`${QA_API}/__qa/phone-verified`, { data: { email } })).ok()).toBeTruthy();
  const taskIds = async () => new Set(((await (await page.request.get("/api/backend/privat/tasks")).json()) as { id: string; kind: string }[])
    .filter((t) => t.kind === "call").map((t) => t.id));

  // 1. Proposal: nothing dialled; reload twice; still nothing.
  await proposeCall(page);
  await evidence(page, info, "X11", "proposal");
  let ids = await taskIds();
  expect(ids.size).toBe(1);
  expect(await mine(page, ids)).toHaveLength(0);
  await page.reload();
  await waitIdle(page);
  await page.goto("/privat/dag");
  await waitIdle(page);
  expect(await mine(page, ids)).toHaveLength(0);

  // 2. «Afvis»: nothing dialled, also not after a reload.
  await page.goto("/privat/samtale");
  await waitIdle(page);
  await chat(page).getByRole("button", { name: "Afvis" }).last().click();
  await waitIdle(page);
  await expect(chat(page).getByText("Opkaldet er afvist").last()).toBeVisible();
  await page.reload();
  await waitIdle(page);
  await page.waitForTimeout(2000);  // the QA worker drains every second
  expect(await mine(page, ids)).toHaveLength(0);

  // 3. A new proposal, approved with a double click: exactly one call.
  await proposeCall(page);
  ids = await taskIds();
  expect(ids.size).toBe(2);
  expect(await mine(page, ids)).toHaveLength(0);
  const approve = chat(page).getByRole("button", { name: "Godkend opkald" }).last();
  await expect(approve).toBeEnabled();
  await approve.dblclick();
  await expect(chat(page).getByText(/Ringer til .* …/).last()).toBeVisible({ timeout: 20_000 });
  await evidence(page, info, "X11", "approved");
  await page.reload();
  await waitIdle(page);
  await page.waitForTimeout(2000);
  const calls = await mine(page, ids);
  expect(calls, JSON.stringify(calls.map((c) => c.payload.metadata))).toHaveLength(1);
});
