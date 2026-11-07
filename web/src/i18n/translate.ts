import type { Locale } from "./config";
import { priceVars } from "@/lib/markets";

export type Messages = Record<string, unknown>;
export type Vars = Record<string, string | number>;
export type T = (key: string, vars?: Vars) => string;

function lookup(messages: Messages, key: string): unknown {
  let cur: unknown = messages;
  for (const part of key.split(".")) {
    if (cur === null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

/** "Hej {name}" + {name: "Anna"} → "Hej Anna". Plurals: "{n|én samtale|# samtaler}" picks by n (1 → first). */
export function format(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)(?:\|([^|}]*)\|([^}]*))?\}/g, (whole, name: string, one?: string, many?: string) => {
    const v = vars[name];
    if (v === undefined) return whole;
    if (one !== undefined && many !== undefined) return (Number(v) === 1 ? one : many).replace(/#/g, String(v));
    return String(v);
  });
}

/** The default variables of a language: the market's price tokens ({pMonthly}, {pBasis} …, see lib/markets.ts). */
export function defaultVars(locale?: Locale): Vars | undefined {
  return locale ? priceVars(locale) : undefined;
}

/** A translator over `messages` (the current locale) with Danish as fallback; a missing key shows the key itself so
 *  it is visible, never an empty string. With a `locale`, the market's price tokens are filled in automatically
 *  (variables passed by the caller win). */
export function makeT(messages: Messages, fallback: Messages, prefix?: string, locale?: Locale): T {
  const defaults = defaultVars(locale);
  return (key, vars) => {
    const full = prefix ? `${prefix}.${key}` : key;
    const v = lookup(messages, full) ?? lookup(fallback, full);
    return typeof v === "string" ? format(v, defaults ? { ...defaults, ...vars } : vars) : full;
  };
}

function formatDeep(x: unknown, vars: Vars): unknown {
  if (typeof x === "string") return x.includes("{") ? format(x, vars) : x;
  if (Array.isArray(x)) return x.map((v) => formatDeep(v, vars));
  if (x && typeof x === "object") return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, formatDeep(v, vars)]));
  return x;
}

/** Raw (non-string) values: arrays and objects such as lists of features. With a `locale`, price tokens inside the
 *  strings are filled in too. */
export function makeRaw(messages: Messages, fallback: Messages, locale?: Locale) {
  const defaults = defaultVars(locale);
  return <V = unknown>(key: string): V => {
    const v = lookup(messages, key) ?? lookup(fallback, key);
    return (defaults ? formatDeep(v, defaults) : v) as V;
  };
}

export function numberFormat(locale: Locale) {
  return new Intl.NumberFormat(locale === "no" ? "nb" : locale);
}
