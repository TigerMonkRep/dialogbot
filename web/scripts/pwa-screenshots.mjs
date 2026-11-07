// Manifest screenshots (public/screenshots/*.png) rendered from the approved app-shell mockup
// (out/mockups/pwa-shell.html): the phone frames without the device chrome at 390×844 (narrow) and the same shell
// laid out as the desktop app at 1280×800 (wide). They are illustrations of the app shell, not captures of a live
// account. Run: node scripts/pwa-screenshots.mjs [path/to/pwa-shell.html]
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright";

const src = process.argv[2] ?? new URL("../../../out/mockups/pwa-shell.html", import.meta.url).pathname;
const outDir = new URL("../public/screenshots/", import.meta.url).pathname;
mkdirSync(outDir, { recursive: true });
const html = readFileSync(src, "utf8");
const style = html.match(/<style>([\s\S]*?)<\/style>/)?.[1] ?? "";

/** The phone blocks in document order: 0 Erhverv «I dag», 1 Privat «Dag», 2 install step, 3 offline. */
const phones = [];
const re = /<div class="phone[^"]*"[^>]*>/g;
let m;
while ((m = re.exec(html))) {
  // Walk to the matching </div> of this phone.
  let depth = 0, i = m.index, start = m.index;
  const tag = /<\/?div\b[^>]*>/g;
  tag.lastIndex = i;
  let t;
  while ((t = tag.exec(html))) {
    depth += t[0].startsWith("</") ? -1 : 1;
    if (depth === 0) { phones.push(html.slice(start, t.index + t[0].length)); break; }
  }
}
if (phones.length < 4) { console.error(`expected 4 phone frames, found ${phones.length}`); process.exit(1); }

const BASE = `${style}
html,body{margin:0;padding:0;background:var(--panel)}
body{display:block}
.phone{border:0;border-radius:0;box-shadow:none;width:390px;min-height:844px;height:844px}
.status{display:none}
.annot,.caption,.statebar{display:none}
.fab{bottom:88px}`;
const narrow = (inner, privat = false) => `<!doctype html><html><head><meta charset="utf-8"><style>${BASE}</style></head><body class="${privat ? "privat" : ""}">${privat ? inner.replace(/class="phone/, 'class="phone privat') : inner}</body></html>`;

/** Desktop: the app header across the top with the pill nav (TabNav), the phone's main content in a centred column,
 *  tabs and FAB hidden – as the shells render it from 640 px up. */
const wide = (inner, privat = false) => `<!doctype html><html><head><meta charset="utf-8"><style>${BASE}
.phone{width:1280px;height:800px;min-height:800px;display:block}
.phone .apphdr{min-height:64px;padding:0 32px}
.phone .apphdr .avatar{margin-left:0}
.phone main{max-width:760px;margin:0 auto;padding:28px 24px !important}
.phone .tabs,.phone .fab{display:none}
.pillnav{display:inline-flex;padding:4px;border:2px solid var(--ink);border-radius:999px;background:var(--paper);margin-left:auto;margin-right:16px}
.pillnav span{min-height:36px;padding:0 16px;border-radius:999px;font-size:14px;font-weight:600;display:inline-flex;align-items:center}
.pillnav span.on{background:var(--ink);color:#fff}
</style></head><body class="${privat ? "privat" : ""}">${(privat ? inner.replace(/class="phone/, 'class="phone privat') : inner)
  .replace(/<span class="avatar">/, privat
    ? '<span class="pillnav"><span class="on">Dag</span><span>Opgaver</span><span>Butik</span><span>Folk</span><span>Konto</span></span><span class="avatar">'
    : '<span class="pillnav"><span class="on">I dag</span><span>Det ved den</span><span>Opkald</span><span>Ugen</span></span><span class="avatar">')}</body></html>`;

const shots = [
  ["erhverv-today-narrow.png", narrow(phones[0]), 390, 844],
  ["erhverv-install-narrow.png", narrow(phones[2]), 390, 844],
  ["erhverv-today-wide.png", wide(phones[0]), 1280, 800],
  ["privat-day-narrow.png", narrow(phones[1], true), 390, 844],
  ["privat-install-narrow.png", narrow(phones[2], true), 390, 844],
  ["privat-day-wide.png", wide(phones[1], true), 1280, 800],
];

const browser = await chromium.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", args: ["--no-sandbox"] });
try {
  for (const [name, page, w, h] of shots) {
    const p = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    await p.setContent(page, { waitUntil: "load" });
    await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: outDir + name, clip: { x: 0, y: 0, width: w, height: h } });
    await p.close();
    console.log("wrote", name, `${w}x${h}`);
  }
} finally { await browser.close(); }
