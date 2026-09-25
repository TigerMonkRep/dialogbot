// Screenshot app routes at 1440/390 and compose them next to the rendered Stitch reference.
// usage: APP_URL=http://localhost:3000 APP_EMAIL=... APP_PASSWORD=... node compare.mjs <route> <stitch-slug-prefix> [out-name]
// Needs `npm run render` first (out/<slug>_{desktop,mobil}-{1440,390}.png).
import fs from 'node:fs'; import path from 'node:path';
import { chromium } from 'playwright';
const [,, route, slug, name = slug] = process.argv;
const APP = process.env.APP_URL ?? 'http://localhost:3000';
const OUT = path.join(path.dirname(new URL(import.meta.url).pathname), 'out');
const b = await chromium.launch();
const ctx0 = await b.newContext();
if (process.env.APP_EMAIL) {
  const p = await ctx0.newPage(); await p.goto(`${APP}/login`);
  await p.fill('input[type=email]', process.env.APP_EMAIL); await p.fill('input[type=password]', process.env.APP_PASSWORD);
  await p.click('button[type=submit]'); await p.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 });
}
const state = await ctx0.storageState(); await ctx0.close();
for (const [w, suffix] of [[1440, 'desktop'], [390, 'mobil']]) {
  const ref = fs.readdirSync(OUT).find((f) => f.startsWith(slug) && f.includes(`_${suffix}-${w}`));
  const ctx = await b.newContext({ viewport: { width: w, height: w === 390 ? 844 : 900 }, storageState: state });
  const p = await ctx.newPage(); await p.goto(`${APP}${route}`, { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
  const appPng = path.join(OUT, `app-${name}-${w}.png`);
  await p.screenshot({ path: appPng, fullPage: true });
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  await ctx.close();
  if (!ref) { console.log(`no reference for ${slug} ${suffix}; app shot: ${appPng}`); continue; }
  const c = await b.newContext({ viewport: { width: w * 2 + 40, height: 800 } });
  const cp = await c.newPage();
  const htmlPath = path.join(OUT, `cmp-${name}-${w}.html`);
  fs.writeFileSync(htmlPath, `<body style="margin:0;display:flex;gap:40px;background:#888;align-items:flex-start">
    <div><div style="font:bold 20px sans-serif;color:#fff;padding:6px">STITCH</div><img src="file://${path.join(OUT, ref)}" style="width:${w}px;display:block"></div>
    <div><div style="font:bold 20px sans-serif;color:#fff;padding:6px">APP ${route}</div><img src="file://${appPng}" style="width:${w}px;display:block"></div></body>`);
  await cp.goto('file://' + htmlPath, { waitUntil: 'load' });
  const cmp = path.join(OUT, `cmp-${name}-${w}.png`); await cp.screenshot({ path: cmp, fullPage: true }); await c.close();
  console.log(`${cmp}${overflow > 0 ? `  (horizontal overflow ${overflow}px)` : ''}`);
}
await b.close();
