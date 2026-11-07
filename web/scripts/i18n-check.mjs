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

// Prices: copy writes {p…} tokens (filled in per market by i18n/translate.ts from lib/markets.ts), never amounts in
// kroner. 1) every {pX} token must be one the translator provides; 2) a EUR market's texts (en, de, es, fr, it) must not
// state an amount in kroner ("2.495 kr.", "4 DKK") – the bug this guards against. Competitors' Danish prices are
// written "DKK 899" (currency first), which is allowed.
const markets = readFileSync(new URL("../src/lib/markets.ts", import.meta.url), "utf8");
const tokens = new Set([...(markets.match(/PRICE_TOKENS = \[([^\]]*)\]/)?.[1] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]));
if (!tokens.size) { console.log("i18n-check: PRICE_TOKENS not found in src/lib/markets.ts"); bad++; }
const EUR_LOCALES = new Set(["en", "de", "es", "fr", "it"]);
const KRONER = /\d[\d.,\u00a0\u202f ]*\s?(?:kr\b\.?|DKK\b|kroner\b|Kronen\b|coronas\b|couronnes\b|corone\b)/;
const strings = (v, p = "") => typeof v === "string" ? [[p, v]] : Array.isArray(v) ? v.flatMap((x, i) => strings(x, `${p}[${i}]`))
  : v && typeof v === "object" ? Object.entries(v).flatMap(([k, x]) => strings(x, p ? `${p}.${k}` : k)) : [];
for (const l of readdirSync(dir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name)) {
  for (const f of readdirSync(join(dir, l)).filter((x) => x.endsWith(".json"))) {
    for (const [key, s] of strings(JSON.parse(readFileSync(join(dir, l, f), "utf8")))) {
      for (const m of s.matchAll(/\{(p[A-Z]\w*)\}/g)) if (!tokens.has(m[1])) { console.log(`${l}/${f}: ${key}: ukendt pris-token {${m[1]}}`); bad++; }
      if (EUR_LOCALES.has(l) && KRONER.test(s)) { console.log(`${l}/${f}: ${key}: beløb i kroner i en EUR-tekst: «${s.match(KRONER)[0]}»`); bad++; }
    }
  }
}
process.exit(bad ? 1 : 0);
