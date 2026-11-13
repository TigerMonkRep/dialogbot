// The US edition (/us): messages/us/*.json are GENERATED from messages/en/*.json – never edit them by hand.
//   node scripts/i18n-us.mjs          write messages/us/
//   node scripts/i18n-us.mjs --check  exit 1 if messages/us/ is not what this script would write (CI)
// 1. American spelling and words (colour → color, enquiry → inquiry, postcode → ZIP code …).
// 2. Tax wording: the US has no VAT – «excl. VAT» becomes «before tax». Texts about a VAT *number* (EU customers'
//    reverse charge) keep the word.
// 3. Phone placeholders become a US number; example amounts in euro are written in dollars.
// 4. src/i18n/us-overrides.json replaces whole texts where the English one is about Denmark ("Enter a Danish phone
//    number"): { "<namespace>": { "<path.to.key>": "text" } }, array items as path.to.list[2][1].
// Prices are not touched here: copy writes {p…} tokens and lib/markets.ts fills in dollars for this locale.
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("../src/i18n/messages/", import.meta.url).pathname;
const overrides = JSON.parse(readFileSync(new URL("../src/i18n/us-overrides.json", import.meta.url), "utf8"));

/** [pattern, replacement] – applied to texts only, never to keys. Case is kept by the capture groups. */
const RULES = [
  [/\b([Cc])olour/g, "$1olor"], [/\b([Ee])nquir/g, (_m, e) => (e === "E" ? "Inquir" : "inquir")],
  [/\b([Cc])entre\b/g, "$1enter"], [/\b([Cc])ancell(ed|ing)\b/g, "$1ancel$2"], [/\b([Pp])rogramme/g, "$1rogram"],
  [/\b([Rr])ecognis/g, "$1ecogniz"], [/\b([Aa])nalys(e|ed|ing)\b/g, "$1nalyz$2"],
  [/\bPostcode\b/g, "ZIP code"], [/\bpostcode\b/g, "ZIP code"],
  [/\bexcl\. VAT\b/g, "before tax"], [/\bexclude VAT\b/g, "exclude tax"], [/\bincl\. VAT\b/g, "incl. tax"],
  [/\binclude VAT\b/g, "include tax"], [/\bincluding VAT\b/g, "including tax"],
  [/\+45 12 34 56 78/g, "+1 512 555 0142"],
  [/€\s?(\d)/g, "$$$1"],   // example amounts written in euro in the English texts («around €50 a month»)
];

const american = (s) => RULES.reduce((t, [re, to]) => t.replace(re, to), s);

function convert(v, path, over, used) {
  if (typeof v === "string") {
    if (path in over) { used.add(path); return over[path]; }
    return american(v);
  }
  if (Array.isArray(v)) return v.map((x, i) => convert(x, `${path}[${i}]`, over, used));
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, convert(x, path ? `${path}.${k}` : k, over, used)]));
  return v;
}

const check = process.argv.includes("--check");
let bad = 0;
if (!check) mkdirSync(join(dir, "us"), { recursive: true });
for (const f of readdirSync(join(dir, "en")).filter((x) => x.endsWith(".json")).sort()) {
  const ns = f.replace(/\.json$/, "");
  const over = overrides[ns] ?? {};
  const used = new Set();
  const out = JSON.stringify(convert(JSON.parse(readFileSync(join(dir, "en", f), "utf8")), "", over, used), null, 2) + "\n";
  for (const k of Object.keys(over)) if (!used.has(k)) { console.log(`us-overrides.json: ${ns}.${k} matches no English text`); bad++; }
  if (check) {
    let cur = "";
    try { cur = readFileSync(join(dir, "us", f), "utf8"); } catch { /* missing */ }
    if (cur !== out) { console.log(`messages/us/${f} is out of date – run: node scripts/i18n-us.mjs`); bad++; }
  } else writeFileSync(join(dir, "us", f), out);
}
if (bad) process.exit(1);
console.log(check ? "i18n-us: messages/us/ is up to date" : "wrote messages/us/ from messages/en/");
