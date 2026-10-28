import Link from "next/link";
import { backend, currentWorkspaceId, isLoggedIn } from "@/lib/api.server";
import { Icon, LogoMark } from "./ui";
export { LogoMark } from "./ui";
import { cookies } from "next/headers";
import { VIEWAS_COOKIE } from "@/lib/config";
import { AccountButton, MoreMenu, PillNav, ViewAsBanner, WorkspaceChip, type NavItem } from "./shell.client";

type Ws = { id: string; name: string; role: string; product_intent: string };
type Me = { display_name: string; email: string; email_verified: boolean; is_platform_operator?: boolean };
type Capability = { key: string; status: "available" | "simulated" | "not_implemented"; environment: string };

/** The ONLY main navigation (Byggevejledning: three pages). */
export const MAIN: NavItem[] = [
  { href: "/app/overview", match: "/app/overview", label: "I dag", icon: "today" },
  { href: "/app/knowledge", match: "/app/knowledge", label: "Det ved den", icon: "menu_book" },
  { href: "/app/inbox", match: "/app/inbox", label: "Opkald", icon: "call" },
];

/** Everything else stays reachable from the compact "Mere" menu. */
export const MORE: NavItem[] = [
  { href: "/app/setup", match: "/app/setup", label: "Opsætningsguide", icon: "tune" },
  { href: "/app/leads", match: "/app/leads", label: "Henvendelser", icon: "contact_support" },
  { href: "/app/bookings", match: "/app/bookings", label: "Bookinger", icon: "calendar_month" },
  { href: "/app/campaigns", match: "/app/campaigns", label: "Kampagner", icon: "campaign" },
  { href: "/app/reception", match: "/app/reception", label: "Reception", icon: "support_agent" },
  { href: "/app/voices", match: "/app/voices", label: "Stemmer", icon: "record_voice_over" },
  { href: "/app/reports", match: "/app/reports", label: "Rapporter", icon: "bar_chart" },
  { href: "/app/tasks", match: "/app/tasks", label: "Opgaver", icon: "task_alt" },
  { href: "/app/notifications", match: "/app/notifications", label: "Notifikationer", icon: "notifications" },
  { href: "/app/billing", match: "/app/billing", label: "Fakturering", icon: "receipt_long" },
  { href: "/app/settings/team", match: "/app/settings", label: "Alle indstillinger", icon: "settings" },
  { href: "/app/help", match: "/app/help", label: "Hjælp", icon: "help_outline" },
];

/* Kept for callers that still import the old names. */
export const NAV: NavItem[] = [...MAIN, ...MORE];
export const SIDE: NavItem[] = NAV;

/** AI status pill. Shows "Aktiv AI" only when the conversation adapter is actually available. */
function AiPill({ live, className = "hidden lg:inline-flex" }: { live: boolean; className?: string }) {
  const cls = live ? "bg-success-soft text-success border-success-soft" : "bg-paper text-muted border-ink border-dashed";
  return (
    <span className={`${className} items-center gap-1.5 px-2.5 py-1 rounded-full border-[1.5px] text-[11px] font-semibold uppercase tracking-[0.08em] whitespace-nowrap ${cls}`} title={live ? undefined : "AI-samtale er ikke tilkoblet endnu"}>
      <span className={`w-1.5 h-1.5 rounded-full ${live ? "bg-success" : "bg-muted"}`} />{live ? "Aktiv AI" : "AI ikke aktiv"}
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
  let unread = 0;
  if (loggedIn && current) {
    try { unread = (await backend<{ unread: number }>(`/workspaces/${current.id}/notifications`)).unread; } catch { /* badge is optional */ }
  }
  return { workspaces, me, current, aiLive, env, unread };
}

/** Notification bell with unread count; the list lives at /app/notifications. */
function Bell({ unread }: { unread: number }) {
  return (
    <Link href="/app/notifications" aria-label={unread ? `Notifikationer, ${unread} ulæste` : "Notifikationer"} className="relative w-11 h-11 rounded-xl flex items-center justify-center text-ink hover:bg-panel">
      <Icon name="notifications" size={22} />
      {unread > 0 && <span className="absolute top-1 right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-highlight text-ink font-display text-[11px] leading-[18px] text-center font-extrabold">{unread > 9 ? "9+" : unread}</span>}
    </Link>
  );
}

function VerifyBanner({ me }: { me: Me | null }) {
  if (!me || me.email_verified) return null;
  return (
    <div className="bg-highlight text-ink border-b-2 border-ink px-4 py-2 text-center text-[14px]">
      Din e-mail er ikke bekræftet. <Link className="underline font-semibold" href="/verify-email">Bekræft nu</Link> for at oprette arbejdsrum.
    </div>
  );
}

const SkipLink = () => <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">Spring til indhold</a>;

/** One shell for the whole logged-in app (Byggevejledning: Dashboard/Viden mockups). */
async function Shell({ children }: { children: React.ReactNode }) {
  const { workspaces, me, current, aiLive, env, unread } = await shellData();
  let viewAs: { name: string; email: string } | null = null;
  try { const raw = (await cookies()).get(VIEWAS_COOKIE)?.value; if (raw) viewAs = JSON.parse(raw); } catch { /* ignore a broken cookie */ }
  return (
    <div className="min-h-dvh bg-panel text-ink flex flex-col">
      <SkipLink />
      {viewAs && <ViewAsBanner who={viewAs} />}
      <header className="sticky top-0 z-50 bg-paper border-b-2 border-ink pt-safe">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 min-h-16 flex items-center gap-3 md:gap-6">
          <div className="flex items-center gap-3 min-w-0">
            <Link href="/app" className="flex items-center gap-2.5 shrink-0" aria-label="Dialogbot – forsiden af appen">
              <LogoMark size={32} />
              <span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span>
            </Link>
            <span className="hidden sm:block"><WorkspaceChip workspaces={workspaces} current={current} plain /></span>
            {env && env !== "prod" && <span className="hidden xl:inline-flex px-2 py-0.5 rounded-full border-[1.5px] border-ink text-[11px] font-semibold uppercase tracking-[0.08em]">{env === "staging" ? "Staging" : "Udvikling"}</span>}
          </div>
          <div className="hidden md:flex items-center gap-3 ml-auto">
            <PillNav items={MAIN} />
            <MoreMenu items={MORE} variant="button" />
          </div>
          <div className="flex items-center gap-1 ml-auto md:ml-0 shrink-0">
            <AiPill live={aiLive} />
            <Bell unread={unread} />
            <div className="md:hidden"><MoreMenu items={MORE} variant="hamburger" /></div>
            <AccountButton me={me} />
          </div>
        </div>
        {/* Mobile: the same three tabs under the header line, with the AI status pill (hidden in the header row at this width). */}
        <div className="md:hidden px-4 pb-3 flex flex-wrap items-center justify-center gap-2">
          <PillNav items={MAIN} className="max-w-full overflow-x-auto no-scrollbar" />
          <AiPill live={aiLive} className="inline-flex shrink-0" />
        </div>
        <VerifyBanner me={me} />
      </header>

      <main id="main" className="flex-grow w-full">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-6 md:py-7 flex flex-col">{children}</div>
      </main>

      <footer className="border-t-2 border-ink bg-paper mt-8">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-4 flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
          <span className="flex items-center gap-2"><LogoMark size={18} /><span className="font-display font-extrabold text-ink">Dialogbot</span><span>·</span><span>AI-reception, der tager telefonen for dig</span></span>
          <span className="flex items-center gap-4">
            {current && <span>{current.name}</span>}
            {env && env !== "prod" && <span>Miljø: {env}</span>}
            <span title={process.env.APP_COMMIT ? `Build ${process.env.APP_COMMIT}` : undefined} className="tabular-nums">{process.env.APP_VERSION}</span>
          </span>
        </div>
      </footer>
    </div>
  );
}

/** Guide shell (setup guide, onboarding). Same shell as the admin pages. */
export async function AppShell({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}

/** Admin shell (all /app/(admin) pages). */
export async function AdminShell({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
