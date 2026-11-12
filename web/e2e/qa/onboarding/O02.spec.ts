import { expect, test } from "@playwright/test";
import type { Server } from "node:http";
import { freshOwner, serve } from "../../helpers";
import { api, colleague, noOverflow, snap } from "./e2b";

/* QA O02 (E2B) – /onboarding/knowledge → trin 1 del A «Hent det fra hjemmesiden» + «Ret det gule» (/app/viden?tab=k05).
 * Krav: "Review extracted facts, services, products, prices, offers, hours and unknowns."
 * Kilde: web/src/app/opsaetning/1/step1.tsx:162-209, app/modules/knowledge (import). Fake AI extraction. */
const ID = "O02";
const SITE = `<!doctype html><html lang="da"><head><title>Fjord Gulv</title></head><body>
  <h1>Fjord Gulv</h1><p>Vi sliber og behandler trægulve i hele Østjylland.</p>
  <h2>Gulvafslibning</h2><p>Afslibning med støvfrit anlæg. Fra 145 kr. pr. m² inkl. moms.</p>
  <h2>Lakering</h2><p>Tre lag slidstærk lak.</p>
  <footer>Fjord Gulv ApS · Havnevej 12 · 8000 Aarhus · CVR 12345674 · Ring på 70 12 34 56 hverdage 8-16</footer></body></html>`;
let server: Server | null = null;
const port = (name: string) => (name.startsWith("mobil") ? 4762 : 4761);

test.afterEach(async () => { await new Promise<void>((r) => (server ? server.close(() => r()) : r())); server = null; });

test("O02 · udtræk vises som grønt/gult, intet er live før godkendelse, «Ret det gule» viser kladderne, dobbeltklik giver ét import", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  server = await serve(port(info.project.name), SITE);
  await page.goto("/opsaetning/1");
  await page.getByLabel("Hjemmesidens adresse").fill(`http://127.0.0.1:${port(info.project.name)}/`);
  await page.getByRole("button", { name: /^Hent/ }).dblclick();
  await expect(page.getByText(/Fundet på/)).toBeVisible({ timeout: 30_000 });
  const tags = page.locator("main li").filter({ hasText: /^(✓|\?) / });
  await expect(tags.filter({ hasText: /Ydelse: Gulvafslibning/ })).toHaveCount(1);
  await expect(tags.filter({ hasText: /Ydelse: Lakering/ })).toHaveCount(1);
  await snap(page, ID, info, "fundet");
  const items = (await api(page).get(`/workspaces/${wsId}/knowledge/items?limit=200`)).body.items as { kind: string; approved_version: unknown; open_draft: { title: string } | null }[];
  const services = items.filter((i) => i.kind === "service");
  expect(services.map((s) => s.open_draft?.title).sort(), "dobbeltklik på «Hent» må ikke give dubletter").toEqual(["Gulvafslibning", "Lakering"]);
  expect(items.every((i) => i.approved_version === null), "intet er godkendt før ejeren godkender").toBeTruthy();
  const live = (await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body.items;
  expect(live).toEqual([]);
  // the yellow ones can be reviewed one by one
  const yellow = page.getByRole("link", { name: "Ret det gule" });
  await expect(yellow).toBeVisible();
  await yellow.click();
  await expect(page).toHaveURL(/\/opsaetning\/viden$/); // since 12/11: the guide's own review step
  await expect(page.getByText("Gulvafslibning").first()).toBeVisible();
  await expect(page.getByText(/Hjemmesiden nævner prisen|145/).first()).toBeVisible();
  await noOverflow(page);
  await snap(page, ID, info, "ret-det-gule");
  // back: approve all → counts agree with the tags shown
  await page.goto("/opsaetning/1");
  // the found panel is gone after navigation – the reviewed items are still drafts
  expect(((await api(page).get(`/workspaces/${wsId}/assistant/knowledge`)).body.items as unknown[]).length).toBe(0);
});

test("O02 · «Godkend alle N»: N er lig med antallet af godkendte emner; derefter live", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  server = await serve(port(info.project.name), SITE);
  await page.goto("/opsaetning/1");
  await page.getByLabel("Hjemmesidens adresse").fill(`http://127.0.0.1:${port(info.project.name)}/`);
  await page.getByRole("button", { name: /^Hent/ }).click();
  const btn = page.getByRole("button", { name: /^Godkend alle \d+/ });
  await expect(btn).toBeVisible({ timeout: 30_000 });
  const n = Number((await btn.innerText()).match(/\d+/)![0]);
  await btn.click();
  await expect(page.getByText("Alt er godkendt og bruges nu af Dialogbot.")).toBeVisible();
  const items = (await api(page).get(`/workspaces/${wsId}/knowledge/items?limit=200`)).body.items as { approved_version: unknown }[];
  expect(items.filter((i) => i.approved_version).length).toBe(n);
  await snap(page, ID, info, "godkendt");
});

test("O02 · hjemmeside der ikke svarer giver en forståelig fejl – ingen hængende «Læser siden …»", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/opsaetning/1");
  await page.getByLabel("Hjemmesidens adresse").fill("http://127.0.0.1:4799/");
  await page.getByRole("button", { name: /^Hent/ }).click();
  await expect(page.locator("main").getByRole("alert")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("button", { name: /^Hent/ })).toBeEnabled();
  await snap(page, ID, info, "fejl");
});

test("O02 · medarbejder: ingen «Godkend alle», og fakta gemmes som kladder", async ({ page, browser }, info) => {
  const { wsId } = await freshOwner(page, info);
  const staff = await colleague(page, browser, info, wsId, "staff");
  server = await serve(port(info.project.name), SITE);
  await staff.page.goto("/opsaetning/1");
  await expect(staff.page.getByText("Dine ændringer gemmes som kladder, som en administrator godkender.")).toBeVisible();
  await staff.page.getByLabel("Hjemmesidens adresse").fill(`http://127.0.0.1:${port(info.project.name)}/`);
  await staff.page.getByRole("button", { name: /^Hent/ }).click();
  await expect(staff.page.getByText(/Fundet på/)).toBeVisible({ timeout: 30_000 });
  await expect(staff.page.getByRole("button", { name: /^Godkend alle/ })).toHaveCount(0);
  // direct API approval is refused for staff
  const items = (await api(staff.page).get(`/workspaces/${wsId}/knowledge/items?limit=200`)).body.items as { open_draft: { id: string } | null }[];
  const draft = items.find((i) => i.open_draft)!.open_draft!.id;
  expect((await api(staff.page).send("POST", `/workspaces/${wsId}/knowledge/versions/${draft}/approve`)).status).toBe(403);
  await snap(staff.page, ID, info, "medarbejder");
  await staff.ctx.close();
});
