// Stamps the build id into the service workers (public/sw-app.js, public/sw.js) so every deploy gets a new cache
// name (dialogbot-<audience>-v<BUILD_ID>) and the browsers see a changed worker. Runs in `npm run prebuild`.
// BUILD_ID = SW_VERSION, else the Vercel commit, else the local git commit, else a timestamp.
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

const dir = new URL("../public/", import.meta.url).pathname;
const files = ["sw-app.js", "sw.js"];

function buildId() {
  if (process.env.SW_VERSION) return process.env.SW_VERSION;
  if (process.env.VERCEL_GIT_COMMIT_SHA) return process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 10);
  try { return execSync("git rev-parse --short=10 HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim(); } catch { /* no git */ }
  return String(Date.now());
}

const id = buildId().replace(/[^A-Za-z0-9._-]/g, "");
for (const f of files) {
  const path = dir + f;
  const src = readFileSync(path, "utf8");
  const out = src.replace(/^const VERSION = "[^"]*";$/m, `const VERSION = "${id}";`);
  if (!/^const VERSION = /m.test(src)) { console.error(`${f}: no VERSION line`); process.exit(1); }
  if (out !== src) writeFileSync(path, out);
  console.log(`${f}: VERSION=${id}`);
}
