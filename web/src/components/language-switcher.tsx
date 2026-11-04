"use client";

import { usePathname, useRouter } from "next/navigation";
import { LOCALES, LOCALE_NAMES, isLocale, isPublicPage, type Locale } from "@/i18n/config";
import { setLocaleCookie, useLocale, useT } from "@/i18n/client";

/** Language picker. On marketing pages it moves to the same page under the new prefix; in the app it stores the
 *  choice (cookie, and the user's profile when `onSaved` persists it) and re-renders. */
export function LanguageSwitcher({ className = "", onSaved, compact = false }: {
  className?: string; onSaved?: (l: Locale) => void;
  /** Header use: short codes ("DA") so the menu fits a phone; the full names stay in the dropdown list. */
  compact?: boolean;
}) {
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
    // The root layout (I18nProvider, <html lang>) is kept across a soft navigation, so a push alone left the
    // client-side texts – this very dropdown, the explainer video – in the old language. Refresh re-fetches it.
    if (isPublicPage(bare)) router.push(bare === "/" ? `/${next}` : `/${next}${bare}`);
    router.refresh();
  }
  const select = (cls: string) => (
    <select value={locale} onChange={(e) => change(e.target.value)} aria-label={t("language")} className={cls}>
      {LOCALES.map((l) => <option key={l} value={l}>{LOCALE_NAMES[l]}</option>)}
    </select>
  );
  if (compact) {
    // A small "DA ▾" pill; the real (invisible) select lies on top, so the phone's own picker opens with full names.
    return (
      <label className={`relative inline-flex items-center min-h-10 px-2.5 rounded-lg border-2 border-ink bg-white text-sm font-semibold text-ink ${className}`}>
        <span aria-hidden="true">{locale.toUpperCase()} ▾</span>
        {select("absolute inset-0 w-full h-full opacity-0 cursor-pointer")}
      </label>
    );
  }
  return (
    <label className={`inline-flex items-center gap-2 text-sm ${className}`}>
      <span className="sr-only">{t("language")}</span>
      {select("min-h-10 rounded-lg border-2 border-ink bg-white px-2 text-sm font-semibold text-ink")}
    </label>
  );
}
