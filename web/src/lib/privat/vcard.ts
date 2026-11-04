/** Minimal vCard (.vcf) reader for contacts exported from an iPhone (Kontakter → Eksportér → Gem i Filer) or Android.
 *  Runs in the browser only – the file never leaves the phone. Handles vCard 2.1/3.0/4.0, folded lines, several cards in
 *  one file, QUOTED-PRINTABLE (2.1) names and several TEL lines (a mobile number is preferred). */
export type VContact = { name: string; phone: string; phones: string[] };

/** RFC 6350 §3.2 unfolding (CRLF + space/tab), plus the 2.1 soft line breaks of QUOTED-PRINTABLE ("=" at line end). */
function unfold(text: string): string[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];
  for (const line of lines) {
    if (/^[ \t]/.test(line) && out.length) { out[out.length - 1] += line.slice(1); continue; }
    if (out.length && /QUOTED-PRINTABLE/i.test(out[out.length - 1].split(":")[0]) && out[out.length - 1].endsWith("=")) {
      out[out.length - 1] = out[out.length - 1].slice(0, -1) + line; continue;
    }
    out.push(line);
  }
  return out;
}

function decodeQP(v: string, charset = "utf-8"): string {
  const bytes: number[] = [];
  for (let i = 0; i < v.length; i++) {
    if (v[i] === "=" && /^[0-9A-F]{2}$/i.test(v.slice(i + 1, i + 3))) { bytes.push(parseInt(v.slice(i + 1, i + 3), 16)); i += 2; }
    else bytes.push(v.charCodeAt(i) & 0xff);
  }
  try { return new TextDecoder(charset).decode(new Uint8Array(bytes)); } catch { return new TextDecoder("utf-8").decode(new Uint8Array(bytes)); }
}

const unescape = (v: string) => v.replace(/\\n/gi, " ").replace(/\\([,;\\])/g, "$1");

type Prop = { name: string; params: string[]; value: string };
function parseLine(line: string): Prop | null {
  const i = line.indexOf(":");
  if (i < 0) return null;
  const head = line.slice(0, i); const raw = line.slice(i + 1);
  const parts = head.split(";");
  const name = parts[0].replace(/^item\d+\./i, "").toUpperCase();
  const params = parts.slice(1).map((p) => p.toUpperCase());
  const qp = params.some((p) => p === "QUOTED-PRINTABLE" || p === "ENCODING=QUOTED-PRINTABLE");
  const cs = params.find((p) => p.startsWith("CHARSET="))?.slice(8).toLowerCase();
  const value = qp ? decodeQP(raw, cs) : raw;
  return { name, params, value };
}

const isMobile = (params: string[]) => params.some((p) => /CELL|MOBILE|IPHONE|TYPE=.*CELL/.test(p));

export function parseVcf(text: string): VContact[] {
  const out: VContact[] = [];
  let cur: { fn?: string; n?: string; tels: { v: string; mobile: boolean }[] } | null = null;
  for (const line of unfold(text)) {
    const p = parseLine(line.trim());
    if (!p) continue;
    if (p.name === "BEGIN" && /VCARD/i.test(p.value)) { cur = { tels: [] }; continue; }
    if (!cur) continue;
    if (p.name === "END" && /VCARD/i.test(p.value)) {
      const n = cur.n ? cur.n.split(";").map(unescape).map((x) => x.trim()) : [];
      const name = (cur.fn ? unescape(cur.fn).trim() : "") || [n[1], n[2], n[0]].filter(Boolean).join(" ").trim();
      const sorted = [...cur.tels.filter((x) => x.mobile), ...cur.tels.filter((x) => !x.mobile)].map((x) => x.v);
      const phones = Array.from(new Set(sorted));
      if (phones.length) out.push({ name: name || phones[0], phone: phones[0], phones });
      cur = null; continue;
    }
    if (p.name === "FN") cur.fn = p.value;
    else if (p.name === "N") cur.n = p.value;
    else if (p.name === "TEL") {
      const v = p.value.replace(/^tel:/i, "").replace(/[^\d+]/g, "");
      if (v.length >= 8) cur.tels.push({ v, mobile: isMobile(p.params) });
    }
  }
  return out;
}
