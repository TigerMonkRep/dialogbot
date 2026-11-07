/** Dialogbot's languages. Danish is the source language: every text is written in Danish first (messages/da/*.json)
 *  and translated into the others. Public pages live under /<locale>/…; the logged-in app keeps its URLs and reads the
 *  language from the LOCALE_COOKIE (set by the switcher, the URL prefix, or the browser's Accept-Language). */
export const LOCALES = ["da", "en", "de", "es", "fr", "it", "no", "sv"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "da";
export const LOCALE_COOKIE = "dlg_lang";
export const LOCALE_HEADER = "x-dlg-locale";

/** Name of each language in that language (for the switcher). */
export const LOCALE_NAMES: Record<Locale, string> = {
  da: "Dansk", en: "English", de: "Deutsch", es: "Español", fr: "Français", it: "Italiano", no: "Norsk", sv: "Svenska",
};
/** BCP-47 tag for <html lang>, hreflang and Intl (Norwegian Bokmål). */
export const HTML_LANG: Record<Locale, string> = {
  da: "da", en: "en", de: "de", es: "es", fr: "fr", it: "it", no: "nb", sv: "sv",
};
export const OG_LOCALE: Record<Locale, string> = {
  da: "da_DK", en: "en_GB", de: "de_DE", es: "es_ES", fr: "fr_FR", it: "it_IT", no: "nb_NO", sv: "sv_SE",
};

/** Message namespaces – one JSON file per namespace per locale (messages/<locale>/<ns>.json). */
export const NAMESPACES = ["common", "site", "landing", "articles", "legal", "auth", "setup", "app", "settings", "widget", "privat", "entry"] as const;
export type Namespace = (typeof NAMESPACES)[number];

export function isLocale(v: unknown): v is Locale {
  return typeof v === "string" && (LOCALES as readonly string[]).includes(v);
}

/** Best match from an Accept-Language header ("nb" and "nn" count as Norwegian). */
export function fromAcceptLanguage(header: string | null | undefined): Locale | null {
  if (!header) return null;
  const tags = header.split(",").map((p) => {
    const [tag, q] = p.trim().split(";q=");
    return { tag: tag.toLowerCase(), q: q ? Number(q) : 1 };
  }).sort((a, b) => b.q - a.q);
  for (const { tag } of tags) {
    const base = tag.split("-")[0];
    const l = base === "nb" || base === "nn" ? "no" : base;
    if (isLocale(l)) return l;
  }
  return null;
}

/** Marketing pages: they exist once per language under /<locale>/… (the files themselves are unprefixed). App, login,
 *  setup and API paths have no prefix – their language is the user's choice (cookie). */
const PUBLIC_EXACT = new Set(["/", "/erhverv", "/priser", "/ai-receptionist", "/ai-telefonsvarer", "/chatbot", "/viden", "/om",
  "/kontakt", "/gdpr", "/privatliv", "/vilkaar", "/proev", "/byggevejledning", "/ambassador/bliv"]);
const PUBLIC_PREFIX = ["/viden/", "/ai-receptionist/"];

export function isPublicPage(path: string): boolean {
  const p = path.split(/[?#]/)[0];
  return PUBLIC_EXACT.has(p) || PUBLIC_PREFIX.some((x) => p.startsWith(x));
}

/** "/priser" → "/en/priser" for marketing pages; anything else unchanged ("/login", "#faq", "https://…"). */
export function localizeHref(locale: Locale, href: string): string {
  if (!href.startsWith("/") || href.startsWith("//") || !isPublicPage(href)) return href;
  return href === "/" ? `/${locale}` : `/${locale}${href}`;
}
