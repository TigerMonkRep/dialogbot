// Render Stitch code.html locally: compile its inline tailwind.config with Tailwind v3,
// swap CDN/Google Fonts for local files, screenshot at the given width.
import fs from 'node:fs'; import path from 'node:path'; import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright';
const S = path.dirname(new URL(import.meta.url).pathname);
const N = path.join(S, 'node_modules');
const FONTS = `
@font-face{font-family:'Inter';font-weight:100 900;src:url(file://${N}/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2) format('woff2')}
@font-face{font-family:'Inter';font-weight:100 900;src:url(file://${N}/@fontsource-variable/inter/files/inter-latin-ext-wght-normal.woff2) format('woff2');unicode-range:U+0100-02BA,U+1E00-1EFF,U+20A0-20C0}
@font-face{font-family:'Manrope';font-weight:200 800;src:url(file://${N}/@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2) format('woff2')}
@font-face{font-family:'Material Symbols Outlined';font-weight:100 700;font-display:block;src:url(file://${N}/material-symbols/material-symbols-outlined.woff2) format('woff2')}
.material-symbols-outlined{font-family:'Material Symbols Outlined';font-weight:normal;font-style:normal;font-size:24px;line-height:1;letter-spacing:normal;text-transform:none;display:inline-block;white-space:nowrap;word-wrap:normal;direction:ltr;-webkit-font-smoothing:antialiased;font-feature-settings:"liga"}`;
// usage: node stitch-render.mjs <refDir> <outDir> [name-filter ...]
//   STITCH_EVAL="switchTab('tab-k03')" STITCH_SUFFIX=k03 → run JS in the page first (e.g. open another tab) and add a suffix.
const [,, refDir, outDir, ...only] = process.argv;
const EVAL = process.env.STITCH_EVAL; const SUFFIX = process.env.STITCH_SUFFIX ? `-${process.env.STITCH_SUFFIX}` : '';
const BLANK = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==';
fs.mkdirSync(outDir, { recursive: true });
const dirs = fs.readdirSync(refDir).filter(d => fs.existsSync(path.join(refDir, d, 'code.html')) && (!only.length || only.some(o => d.includes(o))));
const b = await chromium.launch();
for (const d of dirs) {
  let html = fs.readFileSync(path.join(refDir, d, 'code.html'), 'utf8');
  const cfgM = html.match(/<script id="tailwind-config">([\s\S]*?)<\/script>/);
  const cfgSrc = cfgM[1].replace(/tailwind\.config\s*=\s*/, 'module.exports = ');
  const work = path.join(S, '.work', d); fs.mkdirSync(work, { recursive: true });
  fs.writeFileSync(path.join(work, 'page.html'), html);
  fs.writeFileSync(path.join(work, 'tw.config.cjs'), cfgSrc + `\nmodule.exports.content=[${JSON.stringify(path.join(work,'page.html'))}];\nmodule.exports.plugins=[require(${JSON.stringify(N+'/@tailwindcss/forms')}),require(${JSON.stringify(N+'/@tailwindcss/container-queries')})];\n`);
  fs.writeFileSync(path.join(work, 'in.css'), '@tailwind base;@tailwind components;@tailwind utilities;');
  execFileSync(path.join(N, '.bin/tailwindcss'), ['-c', path.join(work,'tw.config.cjs'), '-i', path.join(work,'in.css'), '-o', path.join(work,'tw.css')], { stdio: 'pipe' });
  html = html.replace(/<script src="https:\/\/cdn\.tailwindcss\.com[^"]*"><\/script>/, `<link rel="stylesheet" href="tw.css"/>`)
             .replace(/<link[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>/g, '')
             // external images are unreachable offline: keep their box, drop the pixels
             .replace(/<img([^>]*?)src="https?:[^"]*"/g, `<img$1src="${BLANK}" style="background:#c8dfda"`)
             .replace(/url\((['"]?)https?:[^)]*\1\)/g, 'none')
             .replace('</head>', `<style>${FONTS}</style></head>`);
  // tw.css must win the cascade like the CDN's injected style (which comes after config); keep order.
  fs.writeFileSync(path.join(work, 'page.html'), html);
  const w = d.endsWith('_mobil') ? 390 : 1440;
  const ctx = await b.newContext({ viewport: { width: w, height: w === 390 ? 844 : 900 } });
  const p = await ctx.newPage();
  await p.goto('file://' + path.join(work, 'page.html'), { waitUntil: 'load' });
  if (EVAL) await p.evaluate(EVAL);
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  await p.screenshot({ path: path.join(outDir, `${d}-${w}${SUFFIX}.png`), fullPage: true });
  await ctx.close(); console.log('ok', d, w);
}
await b.close();
