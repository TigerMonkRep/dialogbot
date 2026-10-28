#!/usr/bin/env node
/**
 * Regenerates the printed material PDFs in web/public/materiale/ from their HTML with Playwright/Chromium.
 *
 *   cd web && node scripts/materiale-pdf.js            # all three
 *   cd web && node scripts/materiale-pdf.js salgsmateriale
 *
 * Needs `playwright` resolvable (it is a devDependency; otherwise NODE_PATH=$(npm root -g)). Each HTML is
 * self-contained (fonts in public/materiale/fonts/), so the PDF is rendered straight from file://, A4,
 * backgrounds on, one .page section per sheet. Fails if a document does not print to the expected page count
 * (one sheet per <section class="page">), so an overflow is caught instead of silently adding blank pages.
 */
const path = require("node:path");
const fs = require("node:fs");
const { chromium } = require("playwright");

const DIR = path.resolve(__dirname, "..", "public", "materiale");
const DOCS = {
  salgsmateriale: "dialogbot-salgsmateriale.pdf",
  opsaetningsmanual: "dialogbot-opsaetningsmanual.pdf",
  ambassadoerhaandbog: "dialogbot-ambassadoerhaandbog.pdf",
};

async function main() {
  const wanted = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(DOCS);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  let failed = false;
  for (const name of wanted) {
    const out = DOCS[name];
    if (!out) throw new Error(`Unknown document "${name}" – one of ${Object.keys(DOCS).join(", ")}`);
    const html = path.join(DIR, `${name}.html`);
    await page.goto("file://" + html, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    await page.emulateMedia({ media: "print" });
    const expected = await page.evaluate(() => document.querySelectorAll("section.page").length);
    // Any section whose content is taller than one A4 sheet (297mm = 1122.5px at 96dpi) would be cut off.
    const overflow = await page.evaluate(() =>
      [...document.querySelectorAll("section.page")].map((s, i) => [i + 1, s.scrollHeight - s.clientHeight]).filter(([, d]) => d > 1));
    const target = path.join(DIR, out);
    await page.pdf({ path: target, format: "A4", printBackground: true, preferCSSPageSize: true });
    const size = fs.statSync(target).size;
    const pages = (fs.readFileSync(target, "latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
    const ok = pages === expected && overflow.length === 0;
    if (!ok) failed = true;
    console.log(`${ok ? "ok " : "!! "} ${out}: ${pages} pages (${expected} sections), ${(size / 1024).toFixed(0)} kB` +
      (overflow.length ? ` – overflow on page(s) ${overflow.map(([p, d]) => `${p} (+${d}px)`).join(", ")}` : ""));
  }
  await browser.close();
  if (failed) process.exit(1);
}

main().catch((e) => { console.error(e); process.exit(1); });
