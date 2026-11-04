import Link from "@/i18n/link";
import { getLocale, getT } from "@/i18n/server";
import { LanguageSwitcher } from "./language-switcher";
import "./site-chrome.css";
import { COMPANY } from "./legal-page";
import { ChatWidget } from "./chat-widget";
import { CookieSettingsLink } from "./site-analytics";
import { ChatIcon, MenuIcon, PlayIcon } from "./site-icons";
import { LANDING_PAGES } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

/** Shared chrome for the public site in the "Byggevejledning" design (design-reference/byggevejledning/*.dc.html):
 *  2 px ink rules, the logo mark, the two-door "path switch" (Prøv den | Byggevejledning) and the phone number.
 *  Server component; the floating chat is the only client part. */
export { EMAIL, HOURS, PHONE_DISPLAY, PHONE_INTL, PHONE_TEL } from "@/lib/contact";
import { EMAIL, PHONE_INTL, PHONE_TEL, PHONE_DISPLAY } from "@/lib/contact";

export type Path = "proev" | "byggevejledning";

export async function Logo({ size = 36, textSize = 22, className = "" }: { size?: number; textSize?: number; className?: string }) {
  const t = await getT("common");
  return (
    <Link href="/" aria-label={t("chrome.home")} className={`inline-flex items-center gap-2.5 text-ink no-underline ${className}`}>
      <LogoMark size={size} />
      <span className="font-display font-extrabold tracking-[-0.3px]" style={{ fontSize: textSize }}>Dialogbot</span>
    </Link>
  );
}

/** The mark: Klods-blå rounded square with a white speech bubble. */
export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <span className="inline-flex items-center justify-center bg-accent text-white shrink-0" style={{ width: size, height: size, borderRadius: Math.round(size * 0.28) }}>
      <ChatIcon size={Math.round(size * 0.56)} stroke="#FFFFFF" />
    </span>
  );
}

/** Segmented pill: the same two doors as the front page, always visible. */
export async function PathSwitch({ current }: { current?: Path }) {
  const t = await getT("common");
  const item = (href: string, key: Path, icon: React.ReactNode, label: string, short = label) => {
    const active = current === key;
    return (
      <Link href={href} aria-current={active ? "page" : undefined}
        className={`inline-flex items-center gap-2 min-h-10 px-3 sm:px-4 whitespace-nowrap rounded-full text-sm font-semibold no-underline ${active ? "bg-ink text-white" : "text-ink hover:bg-panel"}`}>
        <span className="hidden sm:inline-flex" aria-hidden="true">{icon}</span>
        <span className="sm:hidden">{short}</span><span className="hidden sm:inline">{label}</span>
      </Link>
    );
  };
  return (
    <nav aria-label={t("chrome.choosePath")} className="inline-flex p-1 rounded-full border-2 border-ink bg-white">
      {item("/proev", "proev", <PlayIcon size={16} />, t("chrome.tryIt"))}
      {item("/byggevejledning", "byggevejledning", <MenuIcon size={16} />, t("chrome.buildGuide"), t("chrome.buildGuideShort"))}
    </nav>
  );
}

export async function SiteHeader({ current, nav, phone = true, badge, navAlways = false }: {
  current?: Path;
  /** In-page anchors (the byggevejledning has them) or a few page links. */
  nav?: [string, string][];
  phone?: boolean;
  /** Small Trin-gul pill next to the logo, e.g. "Ambassadør". */
  badge?: string;
  /** Show the nav on every width (default: only from lg, as on the landing pages). */
  navAlways?: boolean;
}) {
  const t = await getT("common");
  const locale = await getLocale();
  return (
    <header className="border-b-2 border-ink bg-white">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 min-h-[72px] py-3 flex flex-wrap items-center gap-x-6 gap-y-3 sm:gap-x-8">
        <span className="inline-flex items-center gap-2.5">
          <Logo />
          {badge && <span className="inline-flex items-center min-h-6 px-2.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">{badge}</span>}
        </span>
        {nav && (
          <nav aria-label={t("chrome.mainMenu")} className={`${navAlways ? "flex" : "hidden lg:flex"} flex-wrap gap-x-5 gap-y-1 text-[15px] font-medium ml-auto`}>
            {nav.map(([h, l]) => <Link key={h} href={h} className="text-ink no-underline inline-flex items-center min-h-11 hover:text-accent">{l}</Link>)}
          </nav>
        )}
        <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 sm:gap-x-6 ${nav ? "lg:ml-0 ml-auto" : "ml-auto"}`}>
          <PathSwitch current={current} />
          <Link href="/priser" className="inline-flex items-center min-h-11 text-sm font-semibold text-ink no-underline hover:text-accent">{t("chrome.pricing")}</Link>
          <LanguageSwitcher compact />
          {phone && <a href={PHONE_TEL} className="hidden sm:inline-flex items-center min-h-11 text-sm font-semibold text-ink no-underline">{locale === "da" ? PHONE_DISPLAY : PHONE_INTL}</a>}
        </div>
      </div>
    </header>
  );
}

export async function SiteFooter({ compact = false }: { compact?: boolean }) {
  const t = await getT("common");
  const tl = await getT("landing");
  const link = "text-ink no-underline hover:text-accent inline-flex items-center min-h-11 sm:min-h-0";
  const quiet = "text-muted no-underline hover:text-ink inline-flex items-center min-h-8";
  return (
    <footer className="border-t-2 border-ink bg-white mt-auto">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-8 flex flex-col gap-5 text-sm text-muted">
        {/* Row 1: logo | contact. Row 2: legal links | CVR – both rows share the same left and right edges. */}
        <div className="flex flex-wrap items-center justify-between gap-x-10 gap-y-3">
          <Logo size={28} textSize={18} />
          <div className="flex flex-wrap gap-x-6 gap-y-1 items-center">
            <span>{t("chrome.location")}</span>
            <span>{t("chrome.hours")}</span>
            <a href={`mailto:${EMAIL}`} className={link}>{EMAIL}</a>
            <a href={PHONE_TEL} className={link}>{PHONE_INTL}</a>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-x-10 gap-y-2">
          <div className="flex flex-wrap gap-x-6 gap-y-1 items-center">
            <Link href="/privatliv" className={link}>{t("chrome.privacy")}</Link>
            <Link href="/gdpr" className={link}>{t("chrome.gdpr")}</Link>
            <Link href="/vilkaar" className={link}>{t("chrome.terms")}</Link>
            <CookieSettingsLink className={link} />
          </div>
          <span>CVR {COMPANY.cvr}</span>
        </div>
      </div>
      {!compact && (
        <div className="border-t border-line">
          {/* SEO link index: kept in the HTML for crawlers, visually quiet (small, muted, grouped). */}
          <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-6 grid gap-x-10 gap-y-5 text-[13px] leading-6 text-muted sm:grid-cols-3">
            <nav aria-label={t("chrome.pages")} className="flex flex-col gap-1">
              <span className="eyebrow mb-1">{t("chrome.pages")}</span>
              <Link href="/proev" className={quiet}>{t("chrome.tryIt")}</Link>
              <Link href="/byggevejledning" className={quiet}>{t("chrome.buildGuide")}</Link>
              <Link href="/priser" className={quiet}>{t("chrome.pricing")}</Link>
              <Link href="/om" className={quiet}>{t("chrome.about")}</Link>
              <Link href="/gdpr" className={quiet}>{t("chrome.gdprData")}</Link>
              <Link href="/kontakt" className={quiet}>{t("chrome.contact")}</Link>
              <Link href="/login" className={quiet}>{t("chrome.login")}</Link>
              <Link href="/signup" className={quiet}>{t("chrome.signup")}</Link>
            </nav>
            <nav aria-label={t("chrome.knowledge")} className="flex flex-col gap-1">
              <span className="eyebrow mb-1">{t("chrome.knowledge")}</span>
              {LANDING_PAGES.filter((p) => p.href !== "/priser").map((p) => <Link key={p.href} href={p.href} className={quiet}>{tl(`nav.${p.key}`)}</Link>)}
            </nav>
            <nav aria-label={t("chrome.byIndustry")} className="flex flex-col gap-1">
              <span className="eyebrow mb-1">{t("chrome.byIndustry")}</span>
              {INDUSTRIES.map((i) => <Link key={i.slug} href={`/ai-receptionist/${i.slug}`} className={quiet}>{tl(`industries.${i.slug}.plural`)}</Link>)}
            </nav>
          </div>
        </div>
      )}
    </footer>
  );
}

/** Whole-page frame: skip link, header, main, footer and the floating chat. */
export async function SiteChrome({ children, current, nav, chatOpen = false, chat = true, bg = "bg-white", compactFooter = false }: {
  children: React.ReactNode; current?: Path; nav?: [string, string][]; chatOpen?: boolean; chat?: boolean; bg?: string; compactFooter?: boolean;
}) {
  const t = await getT("common");
  return (
    <div className={`min-h-dvh flex flex-col ${bg} text-ink`}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-white">{t("chrome.skip")}</a>
      <SiteHeader current={current} nav={nav} />
      <main id="main" className="flex-1 flex flex-col">{children}</main>
      <SiteFooter compact={compactFooter} />
      {chat && <ChatWidget defaultOpen={chatOpen} />}
    </div>
  );
}
