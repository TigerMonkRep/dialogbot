// Screenshots of every e-mail template in light, dark and phone width.
//
//   python -m scripts.preview_emails var/email-preview        (from the repo root)
//   node web/scripts/shoot-emails.mjs [preview-dir] [out-dir]  (defaults: var/email-preview, docs/email-previews)
//
// Dark mode is emulated in the browser (prefers-color-scheme), so this tests the real @media rules, not a copy.
// The mark is served from web/public/icons so no network is needed.
import { chromium } from "@playwright/test";
import { readdirSync, readFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const dir = resolve(process.argv[2] ?? join(root, "var/email-preview"));
const out = resolve(process.argv[3] ?? join(root, "docs/email-previews"));
mkdirSync(out, { recursive: true });
const mark = readFileSync(join(root, "web/public/icons/icon-192.png"));
const keys = readdirSync(dir).filter((f) => f.endsWith(".html") && !f.includes(".dark.") && f !== "index.html").map((f) => f.replace(/\.html$/, ""));

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const shots = [
  ["light", { width: 640, height: 800 }, "light"],
  ["dark", { width: 640, height: 800 }, "dark"],
  ["mobile", { width: 390, height: 800 }, "light"],
  ["mobile-dark", { width: 390, height: 800 }, "dark"],
];
for (const [name, viewport, scheme] of shots) {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme, deviceScaleFactor: 1 });
  await ctx.route("**/icons/icon-192.png", (r) => r.fulfill({ body: mark, contentType: "image/png" }));
  for (const key of keys) {
    const page = await ctx.newPage();
    await page.goto(`file://${join(dir, key)}.html`);
    await page.screenshot({ path: join(out, `${key}-${name}.png`), fullPage: true });
    await page.close();
  }
  await ctx.close();
}
await browser.close();
console.log(`${keys.length * shots.length} screenshots in ${out}`);
