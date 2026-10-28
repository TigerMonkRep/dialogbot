/** Opsætning (trin 1–3): small pure helpers shared by the pages and the tests. */

export type WeeklyRange = { days: string[]; open: string; close: string };

const DAYS = ["man", "tir", "ons", "tor", "fre", "lør", "søn"];
const KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_ALIAS: Record<string, number> = { man: 0, mandag: 0, tir: 1, tirsdag: 1, ons: 2, onsdag: 2, tor: 3, torsdag: 3, fre: 4, fredag: 4, lør: 5, lørdag: 5, loer: 5, søn: 6, søndag: 6, soen: 6 };

const hhmm = (h: string, m?: string) => `${h.padStart(2, "0")}:${m ?? "00"}`;
const short = (t: string) => (t.endsWith(":00") ? String(Number(t.slice(0, 2))).padStart(2, "0") : t);

/** "Man–fre 07–16; lør 09–12" → weekly ranges. null when the text cannot be read (nothing is saved then). */
export function parseHours(text: string): WeeklyRange[] | null {
  const parts = text.split(/[;\n]/).map((s) => s.trim()).filter(Boolean);
  if (parts.length === 0) return null;
  const out: WeeklyRange[] = [];
  for (const part of parts) {
    const m = part.toLowerCase().match(/^(.+?)\s+(\d{1,2})(?::?(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::?(\d{2}))?(?:\s*(?:\.|kl\.?))?$/);
    if (!m) return null;
    const [, dayPart, h1, m1, h2, m2] = m;
    const idx: number[] = [];
    const range = dayPart.match(/^([a-zæøå]+)\s*[-–—]\s*([a-zæøå]+)$/);
    if (range) {
      const a = DAY_ALIAS[range[1]], b = DAY_ALIAS[range[2]];
      if (a === undefined || b === undefined || b < a) return null;
      for (let i = a; i <= b; i++) idx.push(i);
    } else {
      for (const w of dayPart.split(/\s*(?:,|og|\+)\s*/)) {
        const d = DAY_ALIAS[w.trim()];
        if (d === undefined) return null;
        idx.push(d);
      }
    }
    const open = hhmm(h1, m1), close = hhmm(h2, m2);
    if (Number(h1) > 23 || Number(h2) > 24 || open >= close) return null;
    out.push({ days: idx.map((i) => KEYS[i]), open, close });
  }
  return out;
}

/** Weekly ranges → the short text the owner reads and edits ("Man–fre 07–16"). */
export function hoursText(weekly: WeeklyRange[] | undefined | null): string {
  if (!weekly?.length) return "";
  return weekly.map((r) => {
    const idx = r.days.map((d) => KEYS.indexOf(d)).filter((i) => i >= 0).sort((a, b) => a - b);
    const contiguous = idx.length > 2 && idx.every((v, i) => i === 0 || v === idx[i - 1] + 1);
    const days = contiguous ? `${DAYS[idx[0]]}–${DAYS[idx[idx.length - 1]]}` : idx.map((i) => DAYS[i]).join(" og ");
    return `${days[0].toUpperCase()}${days.slice(1)} ${short(r.open)}–${short(r.close)}`;
  }).join("; ");
}

/** "Aarhus Kommune + 30 km, Silkeborg" → zones. */
export const parseZones = (text: string): string[] => text.split(/[;\n,]/).map((s) => s.trim()).filter(Boolean).slice(0, 50);
export const zonesText = (zones: string[] | undefined | null): string => (zones ?? []).join(", ");

/** The origin of a website address ("https://www.firma.dk/side" → "https://www.firma.dk"), or null. */
export function originOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try { return new URL(/^https?:\/\//i.test(url) ? url : `https://${url}`).origin; } catch { return null; }
}

/** Goals from the four cards on trin 1. Reception capabilities and outbound calls decide the product intent. */
export type Cards = { phone: boolean; booking: boolean; web: boolean; outbound: boolean };
export function goalsFromCards(c: Cards) {
  const reception = c.phone || c.booking || c.web;
  const product_intent = c.outbound ? (reception ? "both" : "campaigns") : "reception";
  const rec = product_intent !== "campaigns";
  return { product_intent, inbound_phone: rec && c.phone, webchat: rec && c.web, callback: rec && (c.phone || c.web), booking: rec && c.booking };
}
export const cardsFromGoals = (g: { product_intent: string; inbound_phone: boolean; webchat: boolean; booking: boolean }): Cards =>
  ({ phone: g.inbound_phone, booking: g.booking, web: g.webchat, outbound: g.product_intent !== "reception" });
