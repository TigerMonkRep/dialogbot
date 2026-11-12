import { expect, test, type Page } from "@playwright/test";
import { freshOwner, shot } from "./helpers";

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "ingen vandret scroll").toBeTruthy();
}

/* Viden fra en fil og indsat tekst (Fürster/Rebotti): upload en lille PDF og indsæt tekst → kladder i køen, grupperet pr.
 * kategori → «Godkend alle i kategorien» → viden aktiv. Kører på 1440 og 390 px. AI er testdoblen (AI_PROVIDER=fake). */

/** A minimal one-page-per-entry PDF (Helvetica, WinAnsi) – built here so the spec carries no binary fixture. */
function pdf(pages: string[]): Buffer {
  const enc = (s: string) => Buffer.from(s, "latin1");
  const objs: Buffer[] = [];
  const n = pages.length;
  objs.push(enc("<< /Type /Catalog /Pages 2 0 R >>"));
  objs.push(enc(`<< /Type /Pages /Kids [${pages.map((_, i) => `${3 + 2 * i} 0 R`).join(" ")}] /Count ${n} >>`));
  const font = 3 + 2 * n;
  pages.forEach((p, i) => {
    const ops = "BT /F1 11 Tf 50 750 Td 14 TL " + p.split("\n").map((l) => `(${l.replace(/[\\()]/g, (c) => `\\${c}`)}) Tj T*`).join(" ") + " ET";
    const stream = enc(ops);
    objs.push(enc(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${4 + 2 * i} 0 R /Resources << /Font << /F1 ${font} 0 R >> >> >>`));
    objs.push(Buffer.concat([enc(`<< /Length ${stream.length} >>\nstream\n`), stream, enc("\nendstream")]));
  });
  objs.push(enc("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"));
  const parts: Buffer[] = [enc("%PDF-1.4\n")];
  let len = parts[0].length;
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(len);
    const b = Buffer.concat([enc(`${i + 1} 0 obj\n`), o, enc("\nendobj\n")]);
    parts.push(b); len += b.length;
  });
  const xref = len;
  parts.push(enc(`xref\n0 ${objs.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`));
  return Buffer.concat(parts);
}

const PDF = pdf([
  "Rebotti prisliste\nGulvafslibning: Afslibning af traegulve. Fra 160 kr. pr. m2 inkl. moms.\nLakering: Tre lag lak. 95 kr. pr. m2 inkl. moms.",
  "Afbestilling: Afbestilling skal ske senest 48 timer foer aftalt tid.\nAabningstider hverdage 7-15",
]);
const TEXT = `Spørgsmål: Skal vi flytte møblerne selv?
Svar: Ja, rummet skal være tømt, når vi kommer.
Spørgsmål: Hvor lang tid tager en afslibning?
Svar: Typisk én dag for et almindeligt hus.
Kontakt: info@rebotti.example
Vi dækker: Aarhus, Silkeborg, Skanderborg`;

async function waitDone(page: Page) {
  await expect(page.getByTestId("import-summary")).toBeVisible({ timeout: 45_000 });
}

test("Viden: upload en PDF og indsæt tekst → kladder grupperet pr. kategori → «Godkend alle i kategorien» gør dem aktive", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/viden");
  // three ways in, side by side
  for (const name of ["Hent fra hjemmesiden", "Upload fil", "Indsæt tekst"]) await expect(page.getByRole("button", { name })).toBeVisible();

  // 1 · a small PDF
  await page.getByRole("button", { name: "Upload fil" }).click();
  await expect(page.getByText("Træk en fil hertil")).toBeVisible();
  await page.locator("#kn-file").setInputFiles({ name: "rebotti-prisliste.pdf", mimeType: "application/pdf", buffer: PDF });
  await waitDone(page);
  await expect(page.getByTestId("import-summary")).toContainText(/Fandt \d+ ting: 2 ydelser/);
  await noOverflow(page);
  await shot(page, info, "viden-fil-opsummering");

  // 2 · pasted text
  await page.getByRole("button", { name: "Indsæt tekst" }).click();
  await page.getByLabel("Tekst med viden").fill(TEXT);
  await page.getByRole("button", { name: "Analysér teksten" }).click();
  await waitDone(page);
  await expect(page.getByTestId("import-summary")).toContainText("2 FAQ");

  // 3 · the review queue, grouped per category; nothing is live yet
  await page.reload();
  const queue = page.locator("#gennemgang");
  await expect(queue.getByRole("heading", { name: "Forslag til gennemgang" })).toBeVisible();
  for (const g of ["service", "faq", "policy", "opening_hours", "contact", "coverage_area"]) await expect(page.getByTestId(`review-${g}`)).toBeVisible();
  await expect(page.getByTestId("review-service")).toContainText("Kilde: rebotti-prisliste.pdf · side 1");
  await expect(page.getByTestId("review-service")).toContainText("Dokumentet nævner prisen");
  let live = (await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json()).items as { title: string; kind: string }[];
  expect(live).toEqual([]);
  await noOverflow(page);
  await shot(page, info, "viden-gennemgang-grupperet");

  // 4 · inline edit one FAQ answer, then «Godkend alle i kategorien» for Ydelser
  const faq = page.getByTestId("review-faq");
  await faq.getByRole("button", { name: "Ret svaret" }).first().click();
  await faq.getByLabel("Svaret", { exact: true }).first().fill("Ja, rummet skal være tømt – vi hjælper gerne med tunge møbler.");
  await faq.getByRole("button", { name: /Gem|Send til godkendelse/ }).first().click();
  await page.getByRole("button", { name: "Godkend alle i kategorien: Ydelser" }).click();
  await expect(page.getByTestId("review-service")).toHaveCount(0, { timeout: 15_000 });
  live = (await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json()).items;
  expect(live.filter((i) => i.kind === "service").map((i) => i.title).sort()).toEqual(["Gulvafslibning", "Lakering"]);
  expect(live.some((i) => i.kind === "known_answer")).toBe(false); // only the category that was approved

  // 5 · «Godkend alle» for the rest
  await page.getByRole("button", { name: /^Godkend alle \(\d+\)$/ }).click();
  await expect(page.locator("#gennemgang")).toHaveCount(0, { timeout: 15_000 });
  live = (await (await page.request.get(`/api/backend/workspaces/${wsId}/assistant/knowledge`)).json()).items;
  expect(live.filter((i) => i.kind === "known_answer")).toHaveLength(2);
  expect(live.some((i) => i.kind === "opening_hours") && live.some((i) => i.kind === "coverage_area")).toBe(true);
  await page.reload();
  await expect(page.getByText("Ja, rummet skal være tømt – vi hjælper gerne med tunge møbler.")).toBeVisible();
  await shot(page, info, "viden-godkendt");
});

test("Viden: en forkert fil afvises med det samme og laver ingen kladder", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.goto("/app/viden");
  await page.getByRole("button", { name: "Upload fil" }).click();
  await page.locator("#kn-file").setInputFiles({ name: "program.pdf", mimeType: "application/pdf", buffer: Buffer.from("MZ\x90\x00 not a pdf") });
  await expect(page.getByRole("alert").filter({ hasText: /understøttes ikke|beskadiget/ })).toBeVisible();
  const items = (await (await page.request.get(`/api/backend/workspaces/${wsId}/knowledge/items`)).json()).items;
  expect(items).toEqual([]);
});
