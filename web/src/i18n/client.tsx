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
