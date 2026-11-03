// Every locale must have exactly the Danish keys (same structure, arrays of the same length). Exit 1 on a difference.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("../src/i18n/messages/", import.meta.url).pathname;
const shape = (v, p = "") => Array.isArray(v) ? v.flatMap((x, i) => shape(x, `${p}[${i}]`))
  : v && typeof v === "object" ? Object.entries(v).flatMap(([k, x]) => shape(x, p ? `${p}.${k}` : k)) : [p];
let bad = 0;
const ref = readdirSync(join(dir, "da")).filter((f) => f.endsWith(".json"));
for (const l of readdirSync(dir, { withFileTypes: true }).filter((d) => d.isDirectory() && d.name !== "da").map((d) => d.name)) {
  for (const f of ref) {
    const a = new Set(shape(JSON.parse(readFileSync(join(dir, "da", f), "utf8"))));
    let b;
    try { b = new Set(shape(JSON.parse(readFileSync(join(dir, l, f), "utf8")))); } catch { console.log(`${l}/${f}: mangler`); bad++; continue; }
    const missing = [...a].filter((k) => !b.has(k));
    const extra = [...b].filter((k) => !a.has(k));
    if (missing.length || extra.length) {
      bad++;
      console.log(`${l}/${f}: ${missing.length} mangler, ${extra.length} ekstra`, missing.slice(0, 5), extra.slice(0, 5));
    }
  }
}
process.exit(bad ? 1 : 0);
