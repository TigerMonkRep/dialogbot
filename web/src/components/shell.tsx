import Link from "next/link";
import { backend, currentWorkspaceId, isLoggedIn } from "@/lib/api.server";
import { Icon } from "./ui";
import { LogoutMenu, MobileNav, WorkspaceChip } from "./shell.client";

type Ws = { id: string; name: string; role: string; product_intent: string };
type Me = { display_name: string; email: string; email_verified: boolean };

/** Stitch app shell: fixed 64px header, logo block, workspace chip, centered nav, status chip + icons. */
export const NAV: [string, string, string, boolean][] = [
  // [href, label, icon, implemented]
  ["/app/setup", "Oversigt", "dashboard", true],
  ["/app/inbox", "Henvendelser", "inbox", false],
  ["/app/setup", "Opsætningsguide (G01)", "navigation", true],
  ["/app/knowledge", "Viden", "menu_book", true],
  ["/app/campaigns", "Kampagner", "campaign", false],
  ["/app/bookings", "Bookinger", "calendar_month", false],
  ["/app/settings/team", "Indstillinger", "settings", true],
];

export async function AppShell({ children, active }: { children: React.ReactNode; active?: string }) {
  const loggedIn = await isLoggedIn();
  let workspaces: Ws[] = [];
  let me: Me | null = null;
  if (loggedIn) {
    try { [workspaces, me] = await Promise.all([backend<Ws[]>("/workspaces"), backend<Me>("/auth/me")]); } catch { /* pages handle auth errors */ }
  }
  const wsId = (await currentWorkspaceId()) ?? workspaces[0]?.id ?? null;
  const current = workspaces.find((w) => w.id === wsId) ?? workspaces[0] ?? null;
  return (
    <div className="min-h-dvh bg-surface">
      <header className="fixed top-0 w-full z-50 bg-surface/85 backdrop-blur-md shadow-[0_1px_8px_rgba(22,78,67,0.06)]">
        <div className="h-16 w-full px-margin lg:px-margin-lg flex items-center justify-between gap-space-lg">
          <div className="flex items-center gap-space-xl shrink-0">
            <Link href="/app" className="flex items-center gap-space-sm">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center"><Icon name="support_agent" size={20} className="text-secondary-fixed" /></div>
              <span className="font-display text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span>
            </Link>
            <div className="hidden md:block h-6 w-px bg-outline-variant/60" />
            <WorkspaceChip workspaces={workspaces} current={current} />
          </div>
          <nav className="hidden xl:flex items-center gap-1 flex-1 justify-center" aria-label="Hovedmenu">
            {NAV.map(([href, label, , impl]) => (
              <Link key={label} href={impl ? href : `/app/not-yet?area=${encodeURIComponent(label)}`}
                className={`px-space-md py-2 rounded-lg text-label-md transition-colors ${active === label ? "bg-primary text-on-primary font-semibold shadow-sm" : "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface"}`}>
                {label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-space-md shrink-0">
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container-high text-on-surface-variant" title="AI-samtale er ikke aktiveret i denne etape">
              <span className="w-2 h-2 rounded-full bg-outline" />
              <span className="text-label-sm font-semibold uppercase tracking-wider">AI ikke aktiv</span>
            </div>
            <Link href="/app/not-yet?area=Notifikationer" className="w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low" aria-label="Notifikationer"><Icon name="notifications" /></Link>
            <Link href="/app/not-yet?area=Hjælp" className="w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:bg-surface-container-low" aria-label="Hjælp"><Icon name="help_outline" /></Link>
            <LogoutMenu me={me} />
            <MobileNav nav={NAV.map(([h, l, i, impl]) => [impl ? h : `/app/not-yet?area=${encodeURIComponent(l)}`, l, i])} />
          </div>
        </div>
        {me && !me.email_verified && (
          <div className="bg-tertiary-fixed text-on-tertiary-fixed px-margin py-2 text-center text-label-md">
            Din e-mail er ikke bekræftet. <Link className="underline font-semibold" href="/verify-email">Bekræft nu</Link> for at oprette arbejdsrum.
          </div>
        )}
      </header>
      <main className="relative pt-16 w-full px-gutter lg:px-gutter-lg py-gutter">
        <div className="mx-auto max-w-[1400px] pb-margin-lg">{children}</div>
      </main>
    </div>
  );
}
