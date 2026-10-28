// Usage: node svg2png.js jobs.json  — jobs: [{svg: path, out: path, width, height, transparent?: bool}]
const fs = require('fs');
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch();
  for (const j of jobs) {
    const page = await browser.newPage({ viewport: { width: j.width, height: j.height }, deviceScaleFactor: 1 });
    const svg = fs.readFileSync(j.svg, 'utf8');
    const bg = j.transparent ? 'transparent' : (j.background || 'transparent');
    await page.setContent(`<html><body style="margin:0;background:${bg};width:${j.width}px;height:${j.height}px;overflow:hidden">` +
      `<div style="width:${j.width}px;height:${j.height}px;display:block">${svg.replace(/<svg /, `<svg style="width:${j.width}px;height:${j.height}px;display:block" `)}</div></body></html>`);
    await page.screenshot({ path: j.out, omitBackground: !!j.transparent, clip: { x: 0, y: 0, width: j.width, height: j.height } });
    await page.close();
    console.log('wrote', j.out);
  }
  await browser.close();
})();
