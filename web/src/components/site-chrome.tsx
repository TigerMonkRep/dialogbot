import Link from "next/link";
import "./site-chrome.css";
import { COMPANY } from "./legal-page";
import { ChatWidget } from "./chat-widget";
import { ChatIcon, MenuIcon, PlayIcon } from "./site-icons";
import { LANDING_PAGES } from "@/lib/site";
import { INDUSTRIES } from "@/lib/industries";

/** Shared chrome for the public site in the "Byggevejledning" design (design-reference/byggevejledning/*.dc.html):
 *  2 px ink rules, the logo mark, the two-door "path switch" (Prøv den | Byggevejledning) and the phone number.
 *  Server component; the floating chat is the only client part. */
export { EMAIL, HOURS, PHONE_DISPLAY, PHONE_INTL, PHONE_TEL } from "@/lib/contact";
import { EMAIL, HOURS, PHONE_INTL, PHONE_TEL, PHONE_DISPLAY } from "@/lib/contact";

export type Path = "proev" | "byggevejledning";

export function Logo({ size = 36, textSize = 22, className = "" }: { size?: number; textSize?: number; className?: string }) {
  return (
    <Link href="/" aria-label="Dialogbot forside" className={`inline-flex items-center gap-2.5 text-ink no-underline ${className}`}>
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
export function PathSwitch({ current }: { current?: Path }) {
  const item = (href: string, key: Path, icon: React.ReactNode, label: string) => {
    const active = current === key;
    return (
      <Link href={href} aria-current={active ? "page" : undefined}
        className={`inline-flex items-center gap-2 min-h-10 px-4 rounded-full text-sm font-semibold no-underline ${active ? "bg-ink text-white" : "text-ink hover:bg-panel"}`}>
        {icon}{label}
      </Link>
    );
  };
  return (
    <nav aria-label="Vælg vej" className="inline-flex p-1 rounded-full border-2 border-ink bg-white">
      {item("/proev", "proev", <PlayIcon size={16} />, "Prøv den")}
      {item("/byggevejledning", "byggevejledning", <MenuIcon size={16} />, "Byggevejledning")}
    </nav>
  );
}

export function SiteHeader({ current, nav, phone = true }: {
  current?: Path;
  /** In-page anchors (the byggevejledning has them). */
  nav?: [string, string][];
  phone?: boolean;
}) {
  return (
    <header className="border-b-2 border-ink bg-white">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 min-h-[72px] py-3 flex flex-wrap items-center gap-x-6 gap-y-3 sm:gap-x-8">
        <Logo />
        {nav && (
          <nav aria-label="Hovedmenu" className="hidden lg:flex flex-wrap gap-x-6 gap-y-1 text-[15px] font-medium ml-auto">
            {nav.map(([h, l]) => <a key={h} href={h} className="text-ink no-underline py-2.5 hover:text-accent">{l}</a>)}
          </nav>
        )}
        <div className={`flex items-center gap-4 sm:gap-6 ${nav ? "lg:ml-0 ml-auto" : "ml-auto"}`}>
          <PathSwitch current={current} />
          {phone && <a href={PHONE_TEL} className="hidden sm:inline-flex items-center min-h-11 text-sm font-semibold text-ink no-underline">{PHONE_DISPLAY}</a>}
        </div>
      </div>
    </header>
  );
}

export function SiteFooter({ compact = false }: { compact?: boolean }) {
  const link = "text-ink no-underline hover:text-accent inline-flex items-center min-h-11 sm:min-h-0";
  const quiet = "text-muted no-underline hover:text-ink inline-flex items-center min-h-8";
  return (
    <footer className="border-t-2 border-ink bg-white mt-auto">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-8 flex flex-wrap items-center justify-between gap-x-10 gap-y-4 text-sm text-muted">
        <Logo size={28} textSize={18} />
        <div className="flex flex-wrap gap-x-6 gap-y-2 items-center">
          <span>Aarhus · Danmark</span>
          <span>{HOURS}</span>
          <a href={`mailto:${EMAIL}`} className={link}>{EMAIL}</a>
          <a href={PHONE_TEL} className={link}>{PHONE_INTL}</a>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2 items-center">
          <Link href="/privatliv" className={link}>Privatliv</Link>
          <Link href="/vilkaar" className={link}>Handelsbetingelser</Link>
          <span>CVR {COMPANY.cvr}</span>
        </div>
      </div>
      {!compact && (
        <div className="border-t border-line">
          {/* SEO link index: kept in the HTML for crawlers, visually quiet (small, muted, grouped). */}
          <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-6 grid gap-x-10 gap-y-5 text-[13px] leading-6 text-muted sm:grid-cols-3">
            <nav aria-label="Sider" className="flex flex-col gap-1">
              <span className="eyebrow mb-1">Sider</span>
              <Link href="/proev" className={quiet}>Prøv den</Link>
              <Link href="/byggevejledning" className={quiet}>Byggevejledning</Link>
              <Link href="/priser" className={quiet}>Priser</Link>
              <Link href="/kontakt" className={quiet}>Kontakt</Link>
              <Link href="/login" className={quiet}>Log ind</Link>
              <Link href="/signup" className={quiet}>Opret konto</Link>
            </nav>
            <nav aria-label="Viden" className="flex flex-col gap-1">
              <span className="eyebrow mb-1">Viden</span>
              {LANDING_PAGES.filter((p) => p.href !== "/priser").map((p) => <Link key={p.href} href={p.href} className={quiet}>{p.label}</Link>)}
            </nav>
            <nav aria-label="AI-receptionist til din branche" className="flex flex-col gap-1">
              <span className="eyebrow mb-1">AI-receptionist til din branche</span>
              {INDUSTRIES.map((i) => <Link key={i.slug} href={`/ai-receptionist/${i.slug}`} className={quiet}>{i.plural}</Link>)}
            </nav>
          </div>
        </div>
      )}
    </footer>
  );
}

/** Whole-page frame: skip link, header, main, footer and the floating chat. */
export function SiteChrome({ children, current, nav, chatOpen = false, chat = true, bg = "bg-white", compactFooter = false }: {
  children: React.ReactNode; current?: Path; nav?: [string, string][]; chatOpen?: boolean; chat?: boolean; bg?: string; compactFooter?: boolean;
}) {
  return (
    <div className={`min-h-dvh flex flex-col ${bg} text-ink`}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-white">Spring til indhold</a>
      <SiteHeader current={current} nav={nav} />
      <main id="main" className="flex-1 flex flex-col">{children}</main>
      <SiteFooter compact={compactFooter} />
      {chat && <ChatWidget defaultOpen={chatOpen} />}
    </div>
  );
}
