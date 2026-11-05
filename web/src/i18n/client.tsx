"use client";

import { createContext, useContext, useMemo } from "react";
import { LOCALE_COOKIE, type Locale } from "./config";
import { makeRaw, makeT, type Messages, type T } from "./translate";

type Ctx = { locale: Locale; messages: Messages; fallback: Messages };
const I18n = createContext<Ctx | null>(null);

/** Put in the root layout with the current locale's messages (and Danish as fallback). */
export function I18nProvider({ locale, messages, fallback, children }: Ctx & { children: React.ReactNode }) {
  const value = useMemo(() => ({ locale, messages, fallback }), [locale, messages, fallback]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

const PETER = /\bPeter(?=s?\b)/g;
const HAN = /\b(han|ham|hans)\b/gi;
const PRONOUNS: Record<string, [string, string, string]> = { han: ["han", "ham", "hans"], hun: ["hun", "hende", "hendes"], den: ["den", "den", "dens"] };

function swap(word: string, pronoun: string): string {
  const next = PRONOUNS[pronoun][["han", "ham", "hans"].indexOf(word.toLowerCase())];
  return word[0] === word[0].toUpperCase() ? next[0].toUpperCase() + next.slice(1) : next;
}

function renamed(x: unknown, name: string, pronoun: string): unknown {
  if (typeof x === "string") {
    const s = x.replace(PETER, name);
    return pronoun === "han" ? s : s.replace(HAN, (w) => swap(w, pronoun));
  }
  if (Array.isArray(x)) return x.map((v) => renamed(v, name, pronoun));
  if (x && typeof x === "object") return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, renamed(v, name, pronoun)]));
  return x;
}

/** Dialogbot Privat: the user named the assistant something other than «Peter» – every text below says that name. */
export function AssistantNameProvider({ name, pronoun, children }: { name: string | null | undefined; pronoun?: string | null; children: React.ReactNode }) {
  const c = useCtx();
  const n = name || "Peter";
  // han/hun/den are Danish words: other languages keep their own pronouns and only get the name.
  const p = c.locale !== "da" ? "han" : pronoun && PRONOUNS[pronoun] ? pronoun : n === "Peter" ? "han" : "den";
  const value = useMemo(() => (n === "Peter" && p === "han" ? c : {
    ...c, messages: renamed(c.messages, n, p) as Ctx["messages"], fallback: renamed(c.fallback, n, p) as Ctx["fallback"],
  }), [c, n, p]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

function useCtx(): Ctx {
  const c = useContext(I18n);
  if (!c) throw new Error("I18nProvider mangler");
  return c;
}

/** `const t = useT("app")` → t("calls.title"). */
export function useT(ns?: string): T {
  const { messages, fallback } = useCtx();
  return useMemo(() => makeT(messages, fallback, ns), [messages, fallback, ns]);
}

export function useRaw() {
  const { messages, fallback } = useCtx();
  return useMemo(() => makeRaw(messages, fallback), [messages, fallback]);
}

export function useLocale(): Locale {
  return useCtx().locale;
}

/** Path for the current language on public pages: lp("/priser") → "/en/priser". */
export function useLocalePath(): (path: string) => string {
  const locale = useLocale();
  return (path) => (!path.startsWith("/") || path.startsWith("//") ? path : path === "/" ? `/${locale}` : `/${locale}${path}`);
}

export function setLocaleCookie(locale: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
}
