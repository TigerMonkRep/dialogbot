import "server-only";
import { cookies, headers } from "next/headers";
import { DEFAULT_LOCALE, LOCALE_COOKIE, LOCALE_HEADER, fromAcceptLanguage, isLocale, type Locale } from "./config";
import { MESSAGES } from "./messages";
import { makeRaw, makeT, type Messages, type T } from "./translate";

/** The request's language: the /<locale>/ prefix (the proxy passes it on as a header), else the user's choice
 *  (cookie), else the browser's Accept-Language, else Danish. */
export async function getLocale(): Promise<Locale> {
  const h = await headers();
  const fromPath = h.get(LOCALE_HEADER);
  if (isLocale(fromPath)) return fromPath;
  const c = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (isLocale(c)) return c;
  return fromAcceptLanguage(h.get("accept-language")) ?? DEFAULT_LOCALE;
}

export function messagesFor(locale: Locale): Messages {
  return (MESSAGES[locale] ?? {}) as Messages;
}

/** `const t = await getT("site")` → t("home.title"). Without a namespace, keys are "ns.key". */
export async function getT(ns?: string): Promise<T> {
  const locale = await getLocale();
  return makeT(messagesFor(locale), messagesFor(DEFAULT_LOCALE), ns);
}

/** Non-string values (arrays of features, FAQ lists …): `const raw = await getRaw(); raw<string[]>("site.home.points")`. */
export async function getRaw() {
  const locale = await getLocale();
  return makeRaw(messagesFor(locale), messagesFor(DEFAULT_LOCALE));
}

/** Path for the current language: lp("/priser") → "/en/priser". Only for public pages; app paths stay unprefixed. */
export async function getLocalePath(): Promise<(path: string) => string> {
  const locale = await getLocale();
  return (path: string) => localePath(locale, path);
}

export function localePath(locale: Locale, path: string): string {
  if (!path.startsWith("/") || path.startsWith("//")) return path;
  return path === "/" ? `/${locale}` : `/${locale}${path}`;
}
