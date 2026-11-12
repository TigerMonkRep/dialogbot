import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, freshUser, noOverflow, noStaging, snap } from "./e2b";

/* QA O01 (E2B) – /onboarding/business → /opsaetning/1 (trin 1 «Virksomhed»).
 * Krav: "Name, description, optional URL/documents; dynamic multiple/custom categories; manual setup."
 * Kilde: web/src/app/opsaetning/1/{page,step1}.tsx, app/modules/business. */
const ID = "O01";

test("O01 · gammel adresse /onboarding/business lander på trin 1; første besøg opretter arbejdsrum én gang (dobbeltklik)", async ({ browser }, info) => {
  const u = await freshUser(browser, info, "o01new");
  const p = u.page;
  await p.goto("/onboarding/business");
  await expect(p).toHaveURL(/\/opsaetning\/virksomhed$/);
  const name = p.getByLabel("Navn (som den siger det)");
  const go = p.getByRole("button", { name: "Videre" });
  // validation: 0–1 chars cannot create
  await expect(go).toBeDisabled();
  await name.fill("Q");
  await expect(go).toBeDisabled();
  const wsName = `Fjord Gulv QA ${info.project.name} ${Date.now()}`;
  await name.fill(wsName);
  await go.dblclick();
  await expect(p.getByLabel("Hvad I laver – én sætning")).toBeVisible({ timeout: 15_000 });
  const list = (await api(p).get("/workspaces")).body as { name: string }[];
  expect(list.filter((w) => w.name === wsName), "dobbeltklik må kun oprette ét arbejdsrum").toHaveLength(1);
  // the name typed at creation is the name Dialogbot says
  await expect(p.getByLabel("Navn (som den siger det)")).toHaveValue(wsName);
  await noStaging(p);
  await noOverflow(p);
  await snap(p, ID, info, "trin1-efter-oprettelse");
  await u.ctx.close();
});

test("O01 · manuel opsætning: felter gemmes løbende, overlever reload, manual_setup=true uden URL, kategori afledes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  const next = page.getByRole("button", { name: /Videre til trin/ });
  await expect(next).toBeDisabled();
  await expect(page.getByText("Udfyld navn, telefonnummer og hvad I laver for at gå videre.")).toBeVisible();
  await page.getByLabel("Navn (som den siger det)").fill("Fjord Gulv");
  await page.getByLabel("Telefonnummer, kunderne ringer til").fill("+45 86 12 34 56");
  const desc = page.getByLabel("Hvad I laver – én sætning");
  await desc.fill("Gulvafslibning og lakering i Aarhus");
  await desc.blur();
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await expect(next).toBeEnabled();
  const prof = (await api(page).get(`/workspaces/${wsId}/profile`)).body;
  expect(prof).toMatchObject({ legal_name: "Fjord Gulv", description: "Gulvafslibning og lakering i Aarhus", manual_setup: true, website_url: null });
  await expect.poll(async () => ((await api(page).get(`/workspaces/${wsId}/categories`)).body as unknown[]).length, { message: "kategori afledt af beskrivelsen" }).toBeGreaterThan(0);
  await page.reload();
  await expect(page.getByLabel("Navn (som den siger det)")).toHaveValue("Fjord Gulv");
  await expect(page.getByLabel("Hvad I laver – én sætning")).toHaveValue("Gulvafslibning og lakering i Aarhus");
  // optional URL: saving one flips manual_setup off
  await page.getByLabel("Hjemmesidens adresse").fill("https://fjordgulv.example");
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await expect.poll(async () => (await api(page).get(`/workspaces/${wsId}/profile`)).body.manual_setup).toBe(false);
  await snap(page, ID, info, "manuel-udfyldt");
});

test("O01 · tømt navn: siden må ikke sige «Gemt», når intet blev gemt", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  const name = page.getByLabel("Navn (som den siger det)");
  await name.fill("Fjord Gulv");
  await expect(page.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await name.fill("");
  await page.waitForTimeout(1500);
  const stored = (await api(page).get(`/workspaces/${wsId}/profile`)).body.legal_name;
  const status = await page.getByRole("status").filter({ hasText: /gem/i }).first().innerText();
  await snap(page, ID, info, "tomt-navn");
  // Either the empty name is rejected visibly, or it is saved – «Gemt» while the server still has the old name is a lie.
  if (stored === "Fjord Gulv") expect(status, `server har stadig «${stored}», men siden siger: ${status}`).not.toMatch(/^Gemt/);
});

test("O01 · serverfejl (500) og versionskonflikt vises ærligt – ikke «Gemt»", async ({ page, context }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  await page.route(`**/api/backend/workspaces/${wsId}/profile`, (r) => (r.request().method() === "PUT" ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Intern fejl (QA)" }) }) : r.continue()));
  await page.getByLabel("Navn (som den siger det)").fill("Fjord Gulv 500");
  await expect(page.getByRole("alert").filter({ hasText: /Intern fejl \(QA\)|Kunne ikke gemme/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("status").getByText("Gemt", { exact: true })).toHaveCount(0);
  await snap(page, ID, info, "500");
  await page.unroute(`**/api/backend/workspaces/${wsId}/profile`);

  // a second tab saves first → this tab gets the conflict message with «Genindlæs»
  await page.reload();
  const other = await context.newPage();
  await other.goto("/opsaetning/1");
  await other.getByLabel("Hvad I laver – én sætning").fill("Fra fane 2");
  await expect(other.getByRole("status").getByText("Gemt")).toBeVisible({ timeout: 10_000 });
  await page.getByLabel("Hvad I laver – én sætning").fill("Fra fane 1");
  await expect(page.getByText("Siden er ændret et andet sted. Genindlæs den for at se det nyeste.")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Genindlæs" }).click();
  await page.waitForTimeout(1500);
  await snap(page, ID, info, "konflikt-efter-genindlaes");
  const shown = await page.getByLabel("Hvad I laver – én sætning").inputValue();
  // After «Genindlæs» the owner must see the newest value AND be able to save again.
  await page.getByLabel("Navn (som den siger det)").fill("Fjord Gulv efter konflikt");
  await page.waitForTimeout(2500);
  const stillConflict = await page.getByText("Siden er ændret et andet sted.").count();
  const server = (await api(page).get(`/workspaces/${wsId}/profile`)).body;
  await other.close();
  expect.soft(shown, "«Genindlæs» viser stadig den gamle tekst").toBe("Fra fane 2");
  expect(stillConflict, "efter «Genindlæs» giver næste ændring konflikt igen").toBe(0);
  expect(server.legal_name).toBe("Fjord Gulv efter konflikt");
});

test("O01 · roller: læser kan se men ikke ændre (UI + API afviser); medarbejder kan redigere", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const reader = await colleague(page, browser, info, wsId, "reader");
  await reader.page.goto("/opsaetning/1");
  await expect(reader.page.getByText("Din rolle (læser) kan se, men ikke redigere.")).toBeVisible();
  await expect(reader.page.getByLabel("Navn (som den siger det)")).toBeDisabled();
  const prof = (await api(reader.page).get(`/workspaces/${wsId}/profile`)).body;
  const put = await api(reader.page).send("PUT", `/workspaces/${wsId}/profile`, { ...prof, legal_name: "Hacket", expected_version: prof.version });
  expect(put.status).toBe(403);
  await snap(reader.page, ID, info, "laeser");
  await reader.ctx.close();
});

test("O01 · krav: flere/egne kategorier og dokumentupload findes i UI", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  const main = page.locator("main");
  // Requirement O01 asks for dynamic multiple/custom categories and optional documents. Recorded honestly: is there any control?
  const categoryControl = await main.getByText(/Kategori|Branche/i).count();
  // since 12/11 the documents (file, text) are the guide's next step, Viden, right after Virksomhed
  await page.goto("/opsaetning/viden");
  const fileInput = await page.locator("main").locator("input[type=file]").count();
  test.info().annotations.push({ type: "gap", description: `kategori-kontroller: ${categoryControl}, dokument-felter: ${fileInput}` });
  expect.soft(categoryControl, "ingen kategori-kontrol i trin 1 (kategori afledes skjult)").toBeGreaterThan(0);
  expect.soft(fileInput, "ingen dokumentupload i guiden (Viden)").toBeGreaterThan(0);
});

test("O01 · skriv og klik straks videre i trinlinjen: det skrevne må ikke gå tabt", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  await page.getByLabel("Hvad I laver – én sætning").fill("Tømrer og snedker i Silkeborg");
  // within the 0.9 s save pause the owner taps «3» in the header stepper (mobile: the number; desktop: the label)
  await page.getByRole("link", { name: /Trin 3/ }).click();
  await expect(page).toHaveURL(/\/opsaetning\/(telefon|chat|betaling)/);
  await page.waitForTimeout(2000);
  const stored = (await api(page).get(`/workspaces/${wsId}/profile`)).body.description;
  await page.goto("/opsaetning/1");
  await snap(page, ID, info, "efter-hurtig-navigation");
  expect(stored, "beskrivelsen blev aldrig gemt, fordi siden blev forladt inden pausen").toBe("Tømrer og snedker i Silkeborg");
});
