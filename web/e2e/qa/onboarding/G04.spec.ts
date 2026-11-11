import { expect, test, type Page } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, completeProfile, snap } from "./e2b";

/* QA G04 (E2B) – kontekstuel hjælp i opsætningen: «Hjælp» → «Jeg hjælper med trin N».
 * Krav: "«Hjælp mig videre», relevant explanation/example, proposed correction, permission limits and support handoff."
 * Kilde: web/src/components/assistant.tsx (step chips setup.assistant.setupChips), setup-shell.tsx:55. */
const ID = "G04";
const open = async (page: Page, n: number) => {
  await page.getByRole("button", { name: "Hjælp" }).click();
  const d = page.getByRole("dialog", { name: `Jeg hjælper med trin ${n}` });
  await expect(d).toBeVisible();
  return d;
};

test("G04 · forklaring pr. trin; Esc lukker; skærmlæser-navn", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  for (const [n, chip, said] of [[1, "Hvad sker der i trin 2?", /forbinder du din kalender/], [3, "Hvordan viderestiller jeg?", /Tast koden i trin 3/]] as const) {
    await page.goto(`/opsaetning/${n}`);
    const d = await open(page, n);
    await d.getByRole("button", { name: chip }).click();
    await expect(d.getByText(said)).toBeVisible();
    await snap(page, ID, info, `trin${n}`);
    await page.keyboard.press("Escape");
    await expect(d).toBeHidden();
  }
});

test("G04 · rettelse godkendt i hjælpen skal stå i trin 1-felterne bagefter – og næste autogem må ikke give konflikt", async ({ page }, info) => {
  test.fail(true, "F-E2B-07-G04: S2 new – En rettelse godkendt i «Hjælp» i trin 1 (åbningstider, telefonnummer) vises ikke i felterne …");
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await page.goto("/opsaetning/1");
  const d = await open(page, 1);
  const ask = d.getByLabel("Skriv, hvad du vil ændre");
  await ask.fill("åbningstider man-fre 7-15");
  await ask.press("Enter");
  const card = d.getByRole("group", { name: /Ændring: Åbningstider/ });
  await card.getByRole("button", { name: "Godkend" }).click();
  await expect(card.getByText(/Godkendt og gemt/)).toBeVisible();
  await ask.fill("telefonnummeret er 70 12 34 56");
  await ask.press("Enter");
  const card2 = d.getByRole("group", { name: /Ændring:/ }).last();
  await card2.getByRole("button", { name: "Godkend" }).click();
  await expect(card2.getByText(/Godkendt og gemt/)).toBeVisible();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(1000);
  const prof = (await api(page).get(`/workspaces/${wsId}/profile`)).body;
  const hoursShown = await page.getByLabel("Åbningstider").inputValue();
  const phoneShown = await page.getByLabel("Telefonnummer, kunderne ringer til").inputValue();
  // now the owner keeps typing in trin 1
  await page.getByLabel("Hvad I laver – én sætning").fill("Gulvafslibning, lakering og olie i Aarhus");
  await page.waitForTimeout(2500);
  await snap(page, ID, info, "efter-rettelse");
  const conflict = await page.getByText("Siden er ændret et andet sted.").count();
  const after = (await api(page).get(`/workspaces/${wsId}/profile`)).body;
  test.info().annotations.push({ type: "state", description: `server phone=${prof.phone}; shown hours="${hoursShown}" phone="${phoneShown}"; conflict=${conflict}; desc=${after.description}` });
  expect.soft(hoursShown, "trin 1 viser ikke de åbningstider, der lige blev godkendt i hjælpen").toMatch(/07.*15/);
  expect.soft(phoneShown.replace(/\s/g, ""), "trin 1 viser det gamle telefonnummer").toContain("70123456");
  expect(conflict, "næste ændring i trin 1 giver versionskonflikt efter en rettelse via hjælpen").toBe(0);
  expect(after.description).toBe("Gulvafslibning, lakering og olie i Aarhus");
  expect(after.phone.replace(/\s/g, ""), "autogem af trin 1 overskrev telefonnummeret fra hjælpen").toContain("70123456");
});

test("G04 · rettighedsgrænse: læser kan spørge, men får ingen ændringskort; API afviser godkend", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  const r = await colleague(page, browser, info, wsId, "reader");
  await r.page.goto("/opsaetning/1");
  const d = await open(r.page, 1);
  await expect(d.getByText("Din rolle kan spørge og se, men ikke ændre. Bed en ejer eller administrator om ændringer.")).toBeVisible();
  const ask = d.getByLabel("Skriv, hvad du vil ændre");
  await ask.fill("åbningstider man-fre 7-15");
  await ask.press("Enter");
  await expect(d.getByText(/kan kun ændres af|kan din rolle ikke ændre/)).toBeVisible();
  await expect(d.getByRole("button", { name: "Godkend" })).toHaveCount(0);
  await snap(r.page, ID, info, "laeser");
  await r.ctx.close();
});

test("G04 · support-overdragelse: hjælpen i opsætningen tilbyder en vej til et menneske/ønske", async ({ page }, info) => {
  test.fail(true, "F-E2B-15-G04: S3 new – Byggevejledning: «Hjælp» i opsætningen har ingen vej til et menneske eller til «Ønsk en …");
  await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  const d = await open(page, 1);
  const ask = d.getByLabel("Skriv, hvad du vil ændre");
  await ask.fill("bla bla");
  await ask.press("Enter");
  await page.waitForTimeout(1200);
  await snap(page, ID, info, "ikke-forstaaet");
  const human = await d.getByRole("link", { name: /Skriv til os|Kontakt|support|Hjælp/i }).count() + await d.getByRole("button", { name: /Ønsk en funktion|Skriv til os/i }).count();
  expect.soft(human, "ingen vej til support/et menneske fra hjælpen i opsætningen").toBeGreaterThan(0);
});
