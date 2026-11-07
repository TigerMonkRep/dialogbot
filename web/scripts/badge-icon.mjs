// Monochrome notification badge (Android status bar): the speech-bubble mark from public/brand/logo-mark.svg, white
// on transparent, 96×96. Used as `badge` by both service workers. Run: node scripts/badge-icon.mjs
import { readFileSync, writeFileSync } from "node:fs";
import sharp from "sharp";

const src = readFileSync(new URL("../public/brand/logo-mark.svg", import.meta.url), "utf8");
const path = src.match(/<path d="([^"]+)"/)?.[1];
if (!path) { console.error("logo-mark.svg: no <path>"); process.exit(1); }
// The mark drawn in a 24-unit box, scaled to fill ~84 % of the badge; the white stroke stays the brand's 2.4 units.
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24">
<path d="${path}" transform="translate(1 2) scale(0.92)" fill="none" stroke="#FFFFFF" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;
const out = new URL("../public/icons/badge-96.png", import.meta.url);
await sharp(Buffer.from(svg)).png().toFile(out.pathname);
console.log("wrote", out.pathname);
