import Link from "next/link";
import { backend, currentWorkspaceId, isLoggedIn } from "@/lib/api.server";
import { LogoutButton, WorkspaceSwitcher } from "./shell.client";

type Ws = { id: string; name: string; role: string; product_intent: string };

/** App shell for authenticated pages: top bar, workspace switcher, primary nav. */
export async function AppShell({ children }: { children: React.ReactNode }) {
  const loggedIn = await isLoggedIn();
  let workspaces: Ws[] = [];
  let me: { display_name: string; email_verified: boolean } | null = null;
  if (loggedIn) {
    try { [workspaces, me] = await Promise.all([backend<Ws[]>("/workspaces"), backend<{ display_name: string; email_verified: boolean }>("/auth/me")]); } catch { /* handled by pages */ }
  }
  const wsId = (await currentWorkspaceId()) ?? workspaces[0]?.id ?? null;
  const nav = [
    ["/app/setup", "Opsætning"], ["/app/knowledge", "Viden"], ["/app/settings/team", "Team"], ["/app/settings/business", "Indstillinger"],
  ];
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
          <Link href="/app" className="text-lg font-extrabold text-primary-dark">Dialogbot</Link>
          <WorkspaceSwitcher workspaces={workspaces} current={wsId} />
          <nav aria-label="Hovedmenu" className="ml-auto flex flex-wrap gap-1 text-sm">
            {nav.map(([href, label]) => (
              <Link key={href} href={href} className="rounded-lg px-3 py-1.5 font-semibold text-primary-dark hover:bg-white/70">{label}</Link>
            ))}
          </nav>
          <span className="hidden text-xs text-muted sm:inline">{me?.display_name}</span>
          <LogoutButton />
        </div>
        {me && !me.email_verified && (
          <div className="border-t border-yellow-200 bg-yellow-50 px-4 py-2 text-center text-xs text-yellow-900">
            Din e-mail er ikke bekræftet. <Link className="underline" href="/verify-email">Bekræft nu</Link> for at oprette arbejdsrum.
          </div>
        )}
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
