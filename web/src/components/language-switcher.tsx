"use client";

import { usePathname, useRouter } from "next/navigation";
import { LOCALES, LOCALE_NAMES, isLocale, isPublicPage, type Locale } from "@/i18n/config";
import { setLocaleCookie, useLocale, useT } from "@/i18n/client";

/** Language picker. On marketing pages it moves to the same page under the new prefix; in the app it stores the
 *  choice (cookie, and the user's profile when `onSaved` persists it) and re-renders. */
export function LanguageSwitcher({ className = "", onSaved }: { className?: string; onSaved?: (l: Locale) => void }) {
  const locale = useLocale();
  const t = useT("common");
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  function change(next: string) {
    if (!isLocale(next) || next === locale) return;
    setLocaleCookie(next);
    onSaved?.(next);
    const seg = pathname.split("/")[1];
    const bare = isLocale(seg) ? pathname.slice(seg.length + 1) || "/" : pathname;
    if (isPublicPage(bare)) router.push(bare === "/" ? `/${next}` : `/${next}${bare}`);
    else router.refresh();
  }
  return (
    <label className={`inline-flex items-center gap-2 text-sm ${className}`}>
      <span className="sr-only">{t("language")}</span>
      <select value={locale} onChange={(e) => change(e.target.value)} aria-label={t("language")}
        className="min-h-10 rounded-lg border-2 border-ink bg-white px-2 text-sm font-semibold text-ink">
        {LOCALES.map((l) => <option key={l} value={l}>{LOCALE_NAMES[l]}</option>)}
      </select>
    </label>
  );
}
