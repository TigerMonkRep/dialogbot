import type { Locale } from "./config";

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

/** A translator over `messages` (the current locale) with Danish as fallback; a missing key shows the key itself so
 *  it is visible, never an empty string. */
export function makeT(messages: Messages, fallback: Messages, prefix?: string): T {
  return (key, vars) => {
    const full = prefix ? `${prefix}.${key}` : key;
    const v = lookup(messages, full) ?? lookup(fallback, full);
    return typeof v === "string" ? format(v, vars) : full;
  };
}

/** Raw (non-string) values: arrays and objects such as lists of features. */
export function makeRaw(messages: Messages, fallback: Messages) {
  return <V = unknown>(key: string): V => (lookup(messages, key) ?? lookup(fallback, key)) as V;
}

export function numberFormat(locale: Locale) {
  return new Intl.NumberFormat(locale === "no" ? "nb" : locale);
}
