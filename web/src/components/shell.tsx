import Link from "next/link";
import { backend, currentWorkspaceId, isLoggedIn } from "@/lib/api.server";
import { Icon } from "./ui";
import { AccountButton, BottomNav, DesktopNav, MoreMenu, SideNav, WorkspaceChip, type NavItem } from "./shell.client";

type Ws = { id: string; name: string; role: string; product_intent: string };
type Me = { display_name: string; email: string; email_verified: boolean };
type Capability = { key: string; status: "available" | "simulated" | "not_implemented"; environment: string };

const notYet = (area: string) => `/app/not-yet?area=${encodeURIComponent(area)}`;

/** Desktop top navigation (Stitch g01 desktop header). Unbuilt areas go to the honest placeholder. */
export const NAV: NavItem[] = [
  { href: "/app/setup", match: "/app/overview", label: "Oversigt", icon: "dashboard" },
  { href: "/app/leads", match: "/app/leads", label: "Henvendelser", icon: "contact_support" },
  { href: "/app/setup", match: "/app/setup", label: "Opsætningsguide (G01)", icon: "tune" },
  { href: "/app/knowledge", match: "/app/knowledge", label: "Viden", icon: "menu_book" },
  { href: notYet("Kampagner"), match: "/app/campaigns", label: "Kampagner", icon: "campaign" },
  { href: notYet("Bookinger"), match: "/app/bookings", label: "Bookinger", icon: "calendar_month" },
  { href: "/app/settings/team", match: "/app/settings", label: "Indstillinger", icon: "settings" },
];

/** Mobile bottom navigation (Stitch g01 mobil): four slots, the last opens the full menu. */
const BOTTOM: NavItem[] = [
  { href: "/app/setup", match: "/app/overview", label: "Oversigt", icon: "dashboard" },
  { href: "/app/inbox", match: "/app/inbox", label: "Indbakke", icon: "inbox" },
  { href: "/app/setup", match: "/app/setup", label: "Opsætning", icon: "tune" },
];

/** AI status pill. Shows "Aktiv AI" only when the conversation adapter is actually available. */
function AiPill({ live, compact = false }: { live: boolean; compact?: boolean }) {
  const cls = live ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant";
  const dot = live ? "bg-secondary animate-pulse" : "bg-outline";
  const label = live ? (compact ? "AI Live" : "Aktiv AI") : "AI ikke aktiv";
  return compact ? (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full ${cls}`} title={live ? undefined : "AI-samtale er ikke tilkoblet endnu"}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} /><span className="font-label-sm text-[10px] uppercase font-bold tracking-wider">{label}</span>
    </span>
  ) : (
    <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full ${cls}`} title={live ? undefined : "AI-samtale er ikke tilkoblet endnu"}>
      <span className={`w-2 h-2 rounded-full ${dot}`} /><span className="font-label-sm text-label-sm font-semibold uppercase tracking-wider">{label}</span>
    </span>
  );
}

async function shellData() {
  const loggedIn = await isLoggedIn();
  let workspaces: Ws[] = [];
  let me: Me | null = null;
  let caps: Capability[] = [];
  if (loggedIn) {
    try {
      const [w, m, c] = await Promise.all([backend<Ws[]>("/workspaces"), backend<Me>("/auth/me"), backend<{ items: Capability[] }>("/integrations/capabilities")]);
      [workspaces, me, caps] = [w, m, c.items];
    } catch { /* pages handle auth errors */ }
  }
  const wsId = (await currentWorkspaceId()) ?? workspaces[0]?.id ?? null;
  const current = workspaces.find((w) => w.id === wsId) ?? workspaces[0] ?? null;
  const aiLive = caps.find((c) => c.key === "ai.conversation")?.status === "available";
  const env = caps[0]?.environment;
  return { workspaces, me, current, aiLive, env };
}

function VerifyBanner({ me }: { me: Me | null }) {
  if (!me || me.email_verified) return null;
  return (
    <div className="bg-tertiary-fixed text-on-tertiary-fixed px-margin py-2 text-center font-label-md text-label-md">
      Din e-mail er ikke bekræftet. <Link className="underline font-semibold" href="/verify-email">Bekræft nu</Link> for at oprette arbejdsrum.
    </div>
  );
}

const SkipLink = () => <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-space-md focus:py-2 focus:rounded-lg focus:bg-primary focus:text-on-primary">Spring til indhold</a>;

/** Guide shell (Stitch G01/A06): top navigation on desktop, compact header + bottom nav on mobile. */
export async function AppShell({ children }: { children: React.ReactNode }) {
  const { workspaces, me, current, aiLive, env } = await shellData();
  const verifyBanner = <VerifyBanner me={me} />;

  return (
    <div className="min-h-dvh bg-surface flex flex-col">
      <SkipLink />

      {/* Desktop header */}
      <header className="hidden md:block fixed top-0 w-full z-50 bg-surface/85 backdrop-blur-md shadow-[0_1px_8px_rgba(22,78,67,0.06)]">
        <div className="h-16 w-full px-margin-lg flex items-center justify-between gap-space-lg">
          <div className="flex items-center gap-space-xl flex-shrink-0">
            <Link href="/app" className="flex items-center gap-space-sm">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center"><Icon name="support_agent" size={20} className="text-secondary-fixed" /></div>
              <span className="font-headline-sm text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span>
            </Link>
            <div className="h-6 w-px bg-outline-variant/60" />
            <WorkspaceChip workspaces={workspaces} current={current} />
          </div>
          <DesktopNav items={NAV} />
          <div className="flex items-center gap-space-md flex-shrink-0">
            <AiPill live={aiLive} />
            <Link href={notYet("Notifikationer")} className="w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface transition-colors" aria-label="Notifikationer"><Icon name="notifications" size={20} /></Link>
            <Link href={notYet("Hjælp")} className="w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface transition-colors" aria-label="Hjælp"><Icon name="help_outline" size={20} /></Link>
            <AccountButton me={me} />
            <div className="xl:hidden"><MoreMenu items={NAV} variant="icon" /></div>
          </div>
        </div>
        {verifyBanner}
      </header>

      {/* Mobile header */}
      <header className="md:hidden fixed top-0 w-full z-50 pt-safe bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="h-16 px-margin flex items-center justify-between gap-space-sm">
          <div className="flex items-center gap-space-sm min-w-0">
            <MoreMenu items={NAV} variant="hamburger" />
            <div className="flex items-center gap-space-xs min-w-0">
              <div className="w-7 h-7 rounded-lg bg-primary-container flex items-center justify-center flex-shrink-0"><Icon name="smart_toy" size={18} className="text-secondary-fixed" /></div>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-space-xs">
                  <span className="font-headline-sm text-headline-sm text-primary leading-none tracking-tight">Dialogbot</span>
                  <AiPill live={aiLive} compact />
                </div>
                <WorkspaceChip workspaces={workspaces} current={current} compact />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-space-xs flex-shrink-0">
            <Link href={notYet("Notifikationer")} aria-label="Notifikationer" className="w-11 h-11 flex items-center justify-center rounded-lg text-primary hover:bg-surface-container transition-colors"><Icon name="notifications" size={22} /></Link>
            <AccountButton me={me} />
          </div>
        </div>
        {verifyBanner}
      </header>

      <main id="main" className="flex-grow w-full pt-16 pb-24 md:pb-0 bg-surface">
        <div className="w-full px-margin pt-space-md pb-space-md md:px-margin-lg md:py-space-xl max-w-[1440px] mx-auto">{children}</div>
      </main>

      <footer className="hidden md:block w-full bg-surface-container-low mt-margin-lg">
        <div className="w-full px-margin-lg py-space-xl flex flex-col md:flex-row items-center justify-between gap-space-md text-on-surface-variant font-body-sm text-body-sm">
          <div className="flex items-center gap-space-sm">
            <span className="font-label-sm text-label-sm font-semibold uppercase tracking-wider text-primary">Dialogbot</span><span>•</span><span>AI-reception, callback og kampagner</span>
          </div>
          <div className="flex items-center gap-space-lg">
            {current && <span>{current.name}</span>}
            {env && <span>Miljø: {env}</span>}
          </div>
        </div>
      </footer>

      <BottomNav items={BOTTOM} more={NAV} />
    </div>
  );
}

/** Admin sidebar (Stitch K01/C01/BK/M screens). Unbuilt areas lead to the honest placeholder. */
export const SIDE: NavItem[] = [
  { href: "/app/setup", match: "/app/setup", label: "Overblik", icon: "grid_view" },
  { href: "/app/inbox", match: "/app/inbox", label: "Indbakke", icon: "inbox" },
  { href: "/app/leads", match: "/app/leads", label: "Henvendelser", icon: "contact_support" },
  { href: notYet("Reception"), match: "/app/reception", label: "Reception", icon: "support_agent" },
  { href: notYet("Kampagner"), match: "/app/campaigns", label: "Kampagner", icon: "campaign" },
  { href: "/app/knowledge", match: "/app/knowledge", label: "Viden", icon: "menu_book" },
  { href: notYet("Bookinger"), match: "/app/bookings", label: "Bookinger", icon: "calendar_today" },
  { href: "/app/reports", match: "/app/reports", label: "Rapporter", icon: "bar_chart" },
  { href: notYet("Fakturering"), match: "/app/billing", label: "Fakturering", icon: "receipt_long" },
  { href: "/app/settings/team", match: "/app/settings", label: "Indstillinger", icon: "settings" },
];
const SIDE_BOTTOM: NavItem[] = [SIDE[0], SIDE[1], SIDE[5], SIDE[4]];

export async function AdminShell({ children }: { children: React.ReactNode }) {
  const { workspaces, me, current, env } = await shellData();
  const envPill = env && (
    <span className="inline-flex items-center gap-space-xs px-space-sm py-0.5 rounded-full bg-secondary-container font-label-sm text-label-sm text-on-secondary-fixed">
      <span className="w-1.5 h-1.5 rounded-full bg-primary" />{env === "prod" ? "Produktion" : env === "staging" ? "Staging" : "Udvikling"}
    </span>
  );
  return (
    <div className="min-h-dvh bg-surface">
      <SkipLink />
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed left-0 top-0 h-full w-64 bg-surface-container-low z-50 flex-col justify-between py-space-lg shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
        <div className="flex flex-col gap-space-lg">
          <Link href="/app" className="px-gutter flex items-center gap-space-sm">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center"><Icon name="support_agent" size={20} className="text-secondary-fixed" /></div>
            <div className="flex flex-col"><span className="font-headline-sm text-headline-sm text-primary tracking-tight">Dialogbot</span><span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">Admin portal</span></div>
          </Link>
          <SideNav items={SIDE} />
        </div>
        {me && (
          <div className="px-space-md">
            <div className="bg-surface-container-lowest p-space-md rounded-xl flex items-center gap-space-md shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0"><Icon name="person" size={18} className="text-on-primary" /></div>
              <div className="flex flex-col min-w-0 flex-1"><span className="font-label-md text-label-md text-on-surface truncate">{me.display_name}</span><span className="font-body-sm text-body-sm text-on-surface-variant truncate">{current?.name}</span></div>
            </div>
          </div>
        )}
      </aside>

      {/* Desktop header */}
      <header className="hidden lg:flex fixed top-0 left-64 right-0 h-16 bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.04)] z-40 items-center justify-between px-gutter-lg">
        <div className="flex items-center gap-space-md">
          <span className="font-headline-sm text-headline-sm text-primary">Dialogbot</span>
          <span className="text-outline-variant font-body-sm" aria-hidden>/</span>
          <WorkspaceChip workspaces={workspaces} current={current} plain />
          {envPill}
        </div>
        <div className="flex items-center gap-space-md">
          <Link href={notYet("Notifikationer")} aria-label="Notifikationer" className="w-9 h-9 rounded-xl bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors"><Icon name="notifications" size={20} /></Link>
          <div className="flex items-center gap-space-sm pl-space-xs"><AccountButton me={me} />{me && <span className="font-label-md text-label-md text-on-surface">{me.display_name}</span>}</div>
        </div>
      </header>

      {/* Mobile / tablet header */}
      <header className="lg:hidden fixed top-0 w-full z-50 pt-safe bg-surface/85 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
        <div className="h-16 px-margin flex items-center justify-between gap-space-sm">
          <div className="flex items-center gap-space-sm min-w-0">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0"><Icon name="support_agent" size={20} className="text-secondary-fixed" /></div>
            <div className="flex flex-col min-w-0">
              <span className="font-headline-sm text-headline-sm text-primary leading-tight">Dialogbot</span>
              <WorkspaceChip workspaces={workspaces} current={current} compact />
            </div>
          </div>
          <div className="flex items-center gap-space-xs flex-shrink-0">
            <Link href={notYet("Notifikationer")} aria-label="Notifikationer" className="w-11 h-11 flex items-center justify-center rounded-lg text-primary hover:bg-surface-container transition-colors"><Icon name="notifications" size={22} /></Link>
            <AccountButton me={me} />
          </div>
        </div>
        <VerifyBanner me={me} />
      </header>

      <div className="lg:pl-64">
        <div className="hidden lg:block pt-16"><VerifyBanner me={me} /></div>
        <main id="main" className="relative pt-16 lg:pt-0 pb-24 lg:pb-0 w-full px-margin lg:px-gutter-lg py-gutter">
          <div className="flex flex-col w-full pt-space-md lg:pt-gutter pb-margin-lg">{children}</div>
        </main>
      </div>

      <BottomNav items={SIDE_BOTTOM} more={SIDE} breakpoint="lg" />
    </div>
  );
}
