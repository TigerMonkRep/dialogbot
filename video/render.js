// node render.js <lang> stills t1,t2,...   → out/<lang>/still-<t>.jpg
// node render.js <lang> video               → out/<lang>/scene-<i>.mp4 (one per scene) then out/<lang>/silent.mp4
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), { spawn, execFileSync } = require('child_process');
const ROOT = __dirname, [lang, mode, arg] = process.argv.slice(2), FPS = 30;
const timing = JSON.parse(fs.readFileSync(path.join(ROOT, 'out', lang, 'timing.json'), 'utf8'));
const out = path.join(ROOT, 'out', lang); fs.mkdirSync(out, { recursive: true });
const types = { '.html': 'text/html', '.json': 'application/json', '.woff2': 'font/woff2' };
const srv = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split('?')[0])); fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream' }); r.end(d); }); });
(async () => {
  await new Promise(r => srv.listen(0, r));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.goto(`http://localhost:${srv.address().port}/scene.html`);
  await p.evaluate(([l, t]) => window.setup(l, t), [lang, timing]);
  if (mode === 'stills') {
    for (const t of arg.split(',').map(Number)) {
      await p.evaluate(t => window.frame(t), t);
      await p.screenshot({ path: path.join(out, `still-${t}.jpg`), type: 'jpeg', quality: 92 });
    }
  } else {
    const bounds = timing.scenes.map((s, i) => [i === 0 ? 0 : s.start, i < timing.scenes.length - 1 ? timing.scenes[i + 1].start : timing.total]);
    const list = [];
    let frameNo = 0;
    for (let i = 0; i < bounds.length; i++) {
      const endFrame = Math.round(bounds[i][1] * FPS), file = path.join(out, `scene-${i}.mp4`), tmp = file.replace('.mp4', '.tmp.mp4');
      const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-crf', '20', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', String(FPS), tmp], { stdio: ['pipe', 'inherit', 'inherit'] });
      for (; frameNo < endFrame; frameNo++) {
        await p.evaluate(t => window.frame(t), frameNo / FPS);
        const buf = await p.screenshot({ type: 'jpeg', quality: 92 });
        if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      }
      ff.stdin.end();
      const code = await new Promise(r => ff.on('close', r));
      if (code !== 0) throw new Error('ffmpeg ' + code);
      fs.renameSync(tmp, file); list.push(`file '${file}'`);
    }
    fs.writeFileSync(path.join(out, 'list.txt'), list.join('\n'));
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(out, 'list.txt'), '-c', 'copy', path.join(out, 'silent.mp4')]);
  }
  await b.close(); srv.close();
})().catch(e => { console.error(e); process.exit(1); });
