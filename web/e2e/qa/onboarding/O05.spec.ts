import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, colleague, completeProfile, noOverflow, snap } from "./e2b";

/* QA O05 (E2B) – /onboarding/assistant. In the byggevejledning the manuscript is not a setup step; it lives in
 * «Alle indstillinger → Hilsen» (ReceptionScript editor) and can be changed through the assistant.
 * Krav: "Greeting, AI introduction, knowledge limits, script preview and human fallback."
 * Kilde: web/src/app/app/(admin)/reception/{page,client}.tsx, app/modules/reception/{router,service}.py. */
const ID = "O05";

test("O05 · ejer: hilsen, navn, «må ikke», overdragelse gemmes; tom linje i spørgsmål fjernes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await page.goto("/app/indstillinger?ark=hilsen");
  const dlg = page.getByRole("dialog").filter({ visible: true }).last();
  const greeting = page.getByLabel("Telefonhilsen");
  await expect(greeting).toBeVisible();
  // AI suggestion may auto-fill (fake provider) – it must not be saved before «Gem manuskript»
  await page.waitForTimeout(1500);
  expect((await api(page).get(`/workspaces/${wsId}/reception/script`)).body.version).toBe(0);
  await greeting.fill("Hej, du har ringet til {virksomhed}.");
  await page.getByLabel("Navn på assistenten (valgfri)").fill("Sofie");
  await page.getByLabel("Det skal assistenten spørge om (ét pr. linje)").fill("navn\n\nadresse\n  \nantal m²");
  await page.getByLabel("Giv straks videre til en medarbejder når …").fill("vandskade eller klage");
  await page.getByLabel("Det må assistenten ikke love eller udtale sig om").fill("endelige priser uden besigtigelse");
  const save = page.getByRole("button", { name: "Gem manuskript" });
  await save.click();
  await expect(page.getByText("Gemt. Assistenten bruger manuskriptet fra næste samtale.")).toBeVisible();
  const s = (await api(page).get(`/workspaces/${wsId}/reception/script`)).body;
  expect(s).toMatchObject({ version: 1, persona_name: "Sofie", collect: ["navn", "adresse", "antal m²"], escalation: "vandskade eller klage" });
  await page.reload();
  await expect(page.getByLabel("Telefonhilsen")).toHaveValue("Hej, du har ringet til {virksomhed}.");
  await noOverflow(page);
  await snap(page, ID, info, "manuskript");
  void dlg;
});

test("O05 · serverfejl ved gem vises, og intet påstås gemt", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=hilsen");
  await page.route(`**/api/backend/workspaces/${wsId}/reception/script`, (r) => (r.request().method() === "PUT" ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal", message: "Intern fejl (QA)" }) }) : r.continue()));
  await page.getByLabel("Telefonhilsen").fill("Hej fra QA");
  await page.getByRole("button", { name: "Gem manuskript" }).click();
  await expect(page.getByText(/Intern fejl \(QA\)|Det lykkedes ikke|Noget gik galt/).first()).toBeVisible();
  await expect(page.getByText("Gemt. Assistenten bruger manuskriptet fra næste samtale.")).toHaveCount(0);
  await snap(page, ID, info, "500");
});

test("O05 · roller: medarbejder kan se men ikke gemme; læser ser kun besked; API afviser", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const staff = await colleague(page, browser, info, wsId, "staff");
  await staff.page.goto("/app/indstillinger?ark=hilsen");
  await expect(staff.page.getByText("Kun ejere og administratorer kan ændre manuskriptet.")).toBeVisible();
  await expect(staff.page.getByLabel("Telefonhilsen")).toBeDisabled();
  const cur = (await api(staff.page).get(`/workspaces/${wsId}/reception/script`)).body;
  expect((await api(staff.page).send("PUT", `/workspaces/${wsId}/reception/script`, { ...cur, greeting: "x", expected_version: cur.version })).status).toBe(403);
  await snap(staff.page, ID, info, "medarbejder");
  await staff.ctx.close();
});

test("O05 · hilsen via assistenten (almindelige ord): før → efter, intet gælder før Godkend", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await completeProfile(page, wsId);
  await page.goto("/app");
  if ((page.viewportSize()?.width ?? 1440) < 1280) await page.getByRole("button", { name: "Ændr noget" }).click();
  const ask = page.getByLabel("Skriv, hvad du vil ændre").filter({ visible: true });
  await ask.fill("Hilsenen skal være: Goddag, du taler med Fjord Gulvs digitale assistent");
  await ask.press("Enter");
  const card = page.getByRole("group", { name: /Ændring:/ }).filter({ visible: true }).last();
  await expect(card).toBeVisible();
  expect((await api(page).get(`/workspaces/${wsId}/reception/script`)).body.greeting ?? "").toBe("");
  await card.getByRole("button", { name: "Godkend" }).click();
  await expect(card.getByText(/Godkendt og gemt/)).toBeVisible();
  expect((await api(page).get(`/workspaces/${wsId}/reception/script`)).body.greeting).toContain("Goddag, du taler med Fjord Gulvs digitale assistent");
  await snap(page, ID, info, "hilsen-via-assistent");
});

test("O05 · ny kunde gemmer en hilsen uden assistentnavn (feltet er «valgfri») – det skal lykkes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=hilsen");
  await page.getByLabel("Telefonhilsen").fill("Hej, du har ringet til {virksomhed}.");
  const res = page.waitForResponse((r) => r.url().endsWith("/reception/script") && r.request().method() === "PUT");
  await page.getByRole("button", { name: "Gem manuskript" }).click();
  const r = await res;
  await page.waitForTimeout(800);
  await snap(page, ID, info, "foerste-gem-uden-navn");
  const body = await r.text();
  expect(r.status(), `første gem af manuskriptet afvises: ${body}`).toBe(200);
  expect((await api(page).get(`/workspaces/${wsId}/reception/script`)).body.version).toBe(1);
});

test("O05 · andet gem i samme åbne ark må ikke give «ændret af en anden»", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/indstillinger?ark=hilsen");
  await page.getByLabel("Navn på assistenten (valgfri)").fill("Sofie");
  await page.getByLabel("Telefonhilsen").fill("Hej, du har ringet til {virksomhed}.");
  await page.getByRole("button", { name: "Gem manuskript" }).click();
  await expect(page.getByText("Gemt. Assistenten bruger manuskriptet fra næste samtale.")).toBeVisible();
  await page.getByLabel("Afslutning").fill("Tak for opkaldet.");
  await page.getByRole("button", { name: "Gem manuskript" }).click();
  await page.waitForTimeout(1500);
  await snap(page, ID, info, "andet-gem");
  await expect(page.getByText("Manuskriptet er ændret af en anden. Genindlæs."), "ejerens eget andet gem vises som konflikt med «en anden»").toHaveCount(0);
  expect((await api(page).get(`/workspaces/${wsId}/reception/script`)).body.version).toBe(2);
});
