import { expect, test, type Page } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, snap } from "./e2b";

/* QA O06 (E2B) – /onboarding/test → «Test mig som kunde» (assistent-panelet) + prøveopkald i trin 3.
 * Krav: "Simulated scenarios, answers and source references; correction and retest."
 * Kilde: web/src/components/assistant.tsx:180-182,215; app/modules/ai/router.py:18 (preview, kun godkendt viden). */
const ID = "O06";

async function openPanel(page: Page) {
  if ((page.viewportSize()?.width ?? 1440) < 1280) await page.getByRole("button", { name: "Ændr noget" }).click();
}

test("O06 · uden godkendt viden: ærlig besked; med viden: svar; ret via assistenten → genkør; viden-revision stiger", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/viden");
  await openPanel(page);
  await page.getByRole("button", { name: "Test mig som kunde" }).filter({ visible: true }).click();
  const q = page.getByLabel("Skriv et spørgsmål, som en kunde ville stille").filter({ visible: true });
  await q.fill("Hvornår har I åbent?");
  await q.press("Enter");
  await expect(page.getByText("Der er endnu ingen godkendt viden at teste mod. Tilføj og godkend noget først.").filter({ visible: true })).toBeVisible();
  await snap(page, ID, info, "ingen-viden");

  // correction: owner sets hours through the same panel, approves → retest answers
  await page.getByRole("button", { name: "Tilbage" }).filter({ visible: true }).click();
  const rev0 = (await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body.knowledge_revision;
  const ask = page.getByLabel("Skriv, hvad du vil ændre").filter({ visible: true });
  await ask.fill("åbningstider man-fre 7-15");
  await ask.press("Enter");
  const card = page.getByRole("group", { name: /Ændring: Åbningstider/ }).filter({ visible: true }).last();
  await card.getByRole("button", { name: "Godkend" }).click();
  await expect(card.getByText(/Godkendt og gemt/)).toBeVisible();
  const k = (await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body;
  expect(k.knowledge_revision).toBeGreaterThan(rev0);
  expect(JSON.stringify(k.items)).toContain("07:00");
  await page.getByRole("button", { name: "Test mig som kunde" }).filter({ visible: true }).click();
  await q.fill("Hvornår har I åbent?");
  await q.press("Enter");
  await expect(page.getByText(/\[fake\] svar på/).filter({ visible: true }).first()).toBeVisible();
  await snap(page, ID, info, "genkoert");
});

test("O06 · serverfejl i testen giver en besked i samtalen – ingen hængende «Tænker …»", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/viden");
  await openPanel(page);
  await page.route(`**/api/backend/workspaces/${wsId}/assistant/preview`, (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Intern fejl (QA)" }) }));
  await page.getByRole("button", { name: "Test mig som kunde" }).filter({ visible: true }).click();
  const q = page.getByLabel("Skriv et spørgsmål, som en kunde ville stille").filter({ visible: true });
  await q.fill("Hvad koster afslibning?");
  await q.press("Enter");
  await expect(page.getByText(/Intern fejl \(QA\)|Det lykkedes ikke/).filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("Tænker …").filter({ visible: true })).toHaveCount(0);
});

test("O06 · læser: ingen kundetest (API 403) og knappen må ikke føre til en fejl", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const r = await colleague(page, browser, info, wsId, "reader");
  expect((await api(r.page).send("POST", `/workspaces/${wsId}/assistant/preview`, { message: "Hej" })).status).toBe(403);
  await r.page.goto("/app/viden");
  await openPanel(r.page);
  const btn = r.page.getByRole("button", { name: "Test mig som kunde" }).filter({ visible: true });
  if (await btn.count()) {
    await btn.click();
    const q = r.page.getByLabel("Skriv et spørgsmål, som en kunde ville stille").filter({ visible: true });
    await q.fill("Hej");
    await q.press("Enter");
    await r.page.waitForTimeout(1500);
    await snap(r.page, ID, info, "laeser-test");
    const txt = await r.page.getByRole("log").filter({ visible: true }).innerText();
    test.info().annotations.push({ type: "reader", description: txt.slice(-300) });
    expect.soft(btn, "læseren tilbydes «Test mig som kunde», som serveren afviser").toHaveCount(0);
  }
  await r.ctx.close();
});

test("O06 · krav: simulerede scenarier og kildehenvisninger i svaret", async ({ page }, info) => {
  test.fail(true, "O06: not-implemented – simulerede scenarier og kildehenvisninger");
  const { wsId } = await freshOwner(page, info);
  const it = (await api(page).send("POST", `/workspaces/${wsId}/knowledge/items`, { kind: "service", title: "Gulvafslibning", content: { price_net_minor: 14500 } })).body;
  await api(page).send("POST", `/workspaces/${wsId}/knowledge/versions/${it.open_draft.id}/approve`);
  const r = await api(page).send("POST", `/workspaces/${wsId}/assistant/preview`, { message: "Hvad koster gulvafslibning?" });
  expect(r.status).toBe(200);
  test.info().annotations.push({ type: "preview-keys", description: Object.keys(r.body).join(",") });
  expect.soft(Object.keys(r.body).some((k) => /source|citation|reference|kilde/i.test(k)), "svaret har ingen kildehenvisning").toBeTruthy();
});
