// QA (X24, i18n-a11y-qa): deeper static i18n checks than scripts/i18n-check.mjs. Read-only; exit 1 on a hard failure.
//   A. Key parity da ↔ every locale, incl. type (string vs list vs object) and empty translations.
//   B. Untranslated Danish in another locale: value identical to da AND Danish-looking (æ/ø/å or Danish words),
//      plus Danish sentences that are not identical (≥ 2 Danish-only function words) in en/de/es/fr/it, and æ/ø in sv.
//   C. Placeholders: the set of {vars} (incl. plural {n|…|…} and price tokens {pX}) equal per key; plural arity kept.
//   D. Hard-coded Danish in components (JSX text / string literals outside t()) – a list for triage, not a failure,
//      because operator pages (/app/operator/**) stay Danish by design (src/i18n/README.md).
// Usage: node scripts/qa-i18n-check.mjs [--json out.json] [--strict-hardcoded]
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("../src/", import.meta.url).pathname;
const dir = join(root, "i18n/messages");
const LOCALES = ["en", "de", "es", "fr", "it", "no", "sv"];
const args = process.argv.slice(2);
const jsonOut = args.includes("--json") ? args[args.indexOf("--json") + 1] : null;

const flat = (v, p = "", out = new Map()) => {
  if (typeof v === "string") out.set(p, v);
  else if (Array.isArray(v)) { out.set(p, { list: v.length }); v.forEach((x, i) => flat(x, `${p}[${i}]`, out)); }
  else if (v && typeof v === "object") { out.set(p, { obj: true }); for (const [k, x] of Object.entries(v)) flat(x, p ? `${p}.${k}` : k, out); }
  else out.set(p, { other: v });
  return out;
};
const load = (l, f) => JSON.parse(readFileSync(join(dir, l, f), "utf8"));
const files = readdirSync(join(dir, "da")).filter((f) => f.endsWith(".json"));

const res = { parity: [], empty: [], untranslated: [], danishProse: [], placeholders: [], priceTokenSwap: [], plural: [], hardcoded: [] };

// Words that are Danish and not (in that spelling) English/German/Spanish/French/Italian/Swedish/Norwegian prose words.
// For Norwegian, only spellings Bokmål does not share: jeres (deres), virksomhed (virksomhet), nogle/nogen (noen),
// efter (etter), sådan (slik), bliver (blir), gør (gjør), meget (mye), spørgsmål (spørsmål), opkald (anrop), hvad (hva).
const DA_ONLY_NO = /\b(jeres|virksomhed\w*|nogle|nogen|efter|sådan|bliver|gør|meget|spørgsmål|opkald\w*|hvad|behøver|tilbage|sidste|kunne\s+lide|sammen\s+med)\b/i;
const DA_WORDS = /(?<![\p{L}])(og|ikke|jeres|vores|også|eller|hvis|kun|bliver|sådan|hvad|hvordan|når|efter|før|til|med|på|af|det|der|en|et|at|som|kan|skal|vil|du|jer|vi|har|er)(?![\p{L}])/giu;
const DA_STRONG = /(?<![\p{L}])(og|ikke|jeres|vores|også|eller|hvis|bliver|sådan|hvad|hvordan|når|efter|før|til|på|af|jer|skal)(?![\p{L}])/giu;
// Proper nouns / Danish institutions that legitimately appear untranslated.
const ALLOW = /(Skattestyrelsen|forskudsopgørelse\w*|Datatilsynet|markedsføringsloven|bogføringsloven|Aarhus|Fürster|Simonsen|B-indkomst|Søren|Mølle|Østergade|Nørre|Århus|Ærø|Brøndby|Køge|Hørsholm|Gråsten|Fjordgulv|Cykelkælderen|Nørgaard Tømrer|Nørgaard|Trøjborg|DDMMÅÅ|Næstved|Frederiksberg|København|Ørsted|Vesterbro|Østerbro|Hvidovre|Lyngby|Klinik|Salon|Dansk Erhverv|Erhvervsstyrelsen|virk\.dk|borger\.dk|mitid|MitID|e-Boks|Mit ?ID)/gi;
const isDanishLooking = (s) => {
  const t = s.replace(ALLOW, "").replace(/https?:\/\/\S+|\S+@\S+|\{[^}]*\}/g, "");
  if (/[æøå]/i.test(t) && t.replace(/[^\p{L}]/gu, "").length > 3) return true;
  const words = new Set([...t.matchAll(DA_WORDS)].map((m) => m[1].toLowerCase()));
  return words.size >= 3;
};

const varsOf = (s) => {
  const names = [], plurals = [];
  for (const m of s.matchAll(/\{(\w+)(?:\|([^|}]*)\|([^}]*))?\}/g)) { names.push(m[1]); if (m[2] !== undefined) plurals.push(m[1]); }
  return { names: [...new Set(names)].sort(), plurals: [...new Set(plurals)].sort() };
};

for (const f of files) {
  const da = flat(load("da", f));
  for (const l of LOCALES) {
    let other;
    try { other = flat(load(l, f)); } catch { res.parity.push({ l, f, key: "*", issue: "file missing/invalid" }); continue; }
    for (const [k, v] of da) {
      if (!other.has(k)) { res.parity.push({ l, f, key: k, issue: "missing" }); continue; }
      const o = other.get(k);
      const kind = (x) => typeof x === "string" ? "string" : x.list !== undefined ? "list" : x.obj ? "object" : "other";
      if (kind(v) !== kind(o)) { res.parity.push({ l, f, key: k, issue: `type ${kind(v)}→${kind(o)}` }); continue; }
      if (typeof v !== "string") continue;
      if (v.trim() && !o.trim()) res.empty.push({ l, f, key: k });
      // C. placeholders
      const a = varsOf(v), b = varsOf(o);
      const nonPrice = (x) => x.filter((n) => !/^p[A-Z]/.test(n) && n !== "num" && n !== "price");
      if (a.names.join() !== b.names.join() && nonPrice(a.names).join() === nonPrice(b.names).join()) res.priceTokenSwap.push({ l, f, key: k, da: a.names, [l]: b.names });
      else if (a.names.join() !== b.names.join()) res.placeholders.push({ l, f, key: k, da: a.names, [l]: b.names, text: o.slice(0, 120) });
      else if (a.plurals.join() !== b.plurals.join() && a.plurals.length) res.plural.push({ l, f, key: k, da: a.plurals, [l]: b.plurals, text: o.slice(0, 120) });
      // B. untranslated Danish
      if (o === v && o.length > 2) {
        const looks = l === "no" ? (DA_ONLY_NO.test(o) || (/[æøå]/i.test(o) && isDanishLooking(o) && DA_ONLY_NO.test(o)))
          : l === "sv" ? (/[æø]/i.test(o.replace(ALLOW, "")) || /\b(jeres|vores|ikke|også|virksomhed)\b/i.test(o))
          : isDanishLooking(o);
        if (looks) res.untranslated.push({ l, f, key: k, text: o.slice(0, 140) });
      } else if (o !== v && ["en", "de", "es", "fr", "it"].includes(l)) {
        const t = o.replace(ALLOW, "").replace(/\{[^}]*\}/g, "");
        const strong = new Set([...t.matchAll(DA_STRONG)].map((m) => m[1].toLowerCase()));
        if (strong.size >= 3 || /[æø]/i.test(t)) res.danishProse.push({ l, f, key: k, text: o.slice(0, 140) });
      } else if (o !== v && l === "sv" && /[æø]/i.test(o.replace(ALLOW, ""))) {
        res.danishProse.push({ l, f, key: k, text: o.slice(0, 140) });
      }
    }
    for (const k of other.keys()) if (!da.has(k)) res.parity.push({ l, f, key: k, issue: "extra" });
  }
}

// D. Hard-coded Danish in components (excluding operator pages, tests, message files and comments).
const walk = (d) => readdirSync(d).flatMap((n) => {
  const p = join(d, n);
  return statSync(p).isDirectory() ? (n === "messages" || n === "node_modules" ? [] : walk(p)) : /\.(tsx|ts)$/.test(n) ? [p] : [];
});
for (const file of walk(root)) {
  const rel = relative(root, file);
  if (/\/operator\//.test(rel) || /\.test\.|\.spec\./.test(rel)) continue;
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    const code = line.replace(/\/\/.*$/, "").replace(/\/\*.*?\*\//g, "");
    if (/^\s*(\*|\/\*|\/\/)/.test(line)) return;
    // JSX text between tags, or string literals, with Danish letters or ≥ 2 strong Danish words.
    const candidates = [...code.matchAll(/>([^<>{}]*[\p{L}][^<>{}]*)</gu)].map((m) => m[1])
      .concat([...code.matchAll(/(["'`])((?:(?!\1)[^\\]|\\.){4,}?)\1/g)].map((m) => m[2]));
    for (const c of candidates) {
      if (/^[\w./@:#?&=%-]+$/.test(c.trim())) continue; // identifiers, paths, classes
      if (/^[a-z0-9 \-:/[\]().%!_]+$/.test(c) && /\b(flex|px-|text-|bg-|rounded|grid|w-|h-|border)/.test(c)) continue; // tailwind
      const t = c.replace(ALLOW, "");
      const strong = new Set([...t.matchAll(DA_STRONG)].map((m) => m[1].toLowerCase()));
      if ((/[æøå]/i.test(t) && /\p{L}{3,}/u.test(t)) || strong.size >= 2) {
        res.hardcoded.push({ file: rel, line: i + 1, text: c.trim().slice(0, 100) });
      }
    }
  });
}

const by = (arr, f) => arr.reduce((m, x) => ((m[f(x)] ??= []).push(x), m), {});
const sect = (name, arr, show = 15) => {
  console.log(`\n## ${name}: ${arr.length}`);
  for (const x of arr.slice(0, show)) console.log("  ", JSON.stringify(x));
  if (arr.length > show) console.log(`   … ${arr.length - show} more`);
};
sect("A. Nøgle-paritet (mangler/ekstra/type)", res.parity);
sect("A. Tomme oversættelser", res.empty);
sect("B. Uoversat dansk (identisk med da)", res.untranslated, 200);
sect("B. Dansk prosa i andre sprog (ikke identisk)", res.danishProse, 200);
sect("C. Placeholder-forskelle", res.placeholders, 200);
sect("C. (advarsel) Pris-token byttet om pr. marked – bevidst, tjekkes i browser", res.priceTokenSwap, 3);
sect("C. Flertalsform mistet i oversættelse", res.plural, 200);
const hcFiles = by(res.hardcoded, (x) => x.file.split("/").slice(0, 3).join("/"));
console.log(`\n## D. Hårdkodet dansk i komponenter (uden for operator): ${res.hardcoded.length} linjer i ${new Set(res.hardcoded.map((x) => x.file)).size} filer`);
for (const [g, xs] of Object.entries(hcFiles).sort((a, b) => b[1].length - a[1].length)) console.log(`   ${String(xs.length).padStart(4)}  ${g}`);
if (jsonOut) writeFileSync(jsonOut, JSON.stringify(res, null, 2));

const hard = res.parity.length + res.empty.length + res.untranslated.length + res.danishProse.length + res.placeholders.length + res.plural.length
  + (args.includes("--strict-hardcoded") ? res.hardcoded.length : 0);
console.log(`\nqa-i18n-check: ${hard ? "FEJL" : "OK"} (${hard} hårde fund)`);
process.exit(hard ? 1 : 0);
