import Link from "next/link";
import { backend, currentWorkspaceId, isLoggedIn } from "@/lib/api.server";
import { LogoMark } from "./ui";
export { LogoMark } from "./ui";
import { cookies } from "next/headers";
import { VIEWAS_COOKIE } from "@/lib/config";
import { AssistantDock } from "./assistant";
import { Avatar, BottomTabs, TabNav, ViewAsBanner, WorkspaceChip, type NavItem } from "./shell.client";

type Ws = { id: string; name: string; role: string; product_intent: string };
type Me = { display_name: string; email: string; email_verified: boolean; is_platform_operator?: boolean };
type Capability = { key: string; status: "available" | "simulated" | "not_implemented"; environment: string };

/** The four pages (Byggevejledningen: one place per question). Aftaler and Kampagner are reached from I dag. */
export const MAIN: NavItem[] = [
  { href: "/app", match: "/app", also: ["/app/aftaler", "/app/kampagner"], label: "I dag", icon: "today" },
  { href: "/app/viden", match: "/app/viden", label: "Det ved den", icon: "menu_book" },
  { href: "/app/opkald", match: "/app/opkald", label: "Opkald", icon: "call" },
  { href: "/app/ugen", match: "/app/ugen", label: "Ugen", icon: "bar_chart" },
];

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
  const env = caps[0]?.environment;
  return { workspaces, me, current, env };
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

/** One shell for the whole logged-in app: header with the four pages and the avatar, bottom tabs on a phone, and the
 *  assistant «Ændr noget» (column on a wide screen, sheet behind a button elsewhere). */
async function Shell({ children }: { children: React.ReactNode }) {
  const { workspaces, me, current, env } = await shellData();
  let viewAs: { name: string; email: string } | null = null;
  try { const raw = (await cookies()).get(VIEWAS_COOKIE)?.value; if (raw) viewAs = JSON.parse(raw); } catch { /* ignore a broken cookie */ }
  return (
    <div className="min-h-dvh bg-panel text-ink flex flex-col">
      <SkipLink />
      {viewAs && <ViewAsBanner who={viewAs} />}
      <header className="sticky top-0 z-30 bg-paper border-b-2 border-ink pt-safe">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 min-h-16 flex items-center gap-3 md:gap-6">
          <div className="flex items-center gap-3 min-w-0">
            <Link href="/app" className="flex items-center gap-2.5 shrink-0" aria-label="Dialogbot – I dag">
              <LogoMark size={32} />
              <span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span>
            </Link>
            <span className="hidden md:block"><WorkspaceChip workspaces={workspaces} current={current} plain /></span>
            {env && env !== "prod" && <span className="hidden xl:inline-flex px-2 py-0.5 rounded-full border-[1.5px] border-ink text-[11px] font-semibold uppercase tracking-[0.08em]">{env === "staging" ? "Staging" : "Udvikling"}</span>}
          </div>
          <div className="hidden sm:flex items-center ml-auto"><TabNav items={MAIN} /></div>
          <div className="flex items-center ml-auto sm:ml-0 shrink-0"><Avatar me={me} /></div>
        </div>
        <VerifyBanner me={me} />
      </header>

      <main id="main" className="flex-grow w-full pb-[92px] sm:pb-0">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-6 md:py-7 flex gap-6 items-start">
          <div className="flex-1 min-w-0 flex flex-col">{children}</div>
          <AssistantDock />
        </div>
      </main>

      <footer className="hidden sm:block border-t-2 border-ink bg-paper mt-8">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-4 flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
          <span className="flex items-center gap-2"><LogoMark size={18} /><span className="font-display font-extrabold text-ink">Dialogbot</span><span>·</span><span>AI-reception, der tager telefonen for dig</span></span>
          <span className="flex items-center gap-4">
            {current && <span>{current.name}</span>}
            {env && env !== "prod" && <span>Miljø: {env}</span>}
            <Link href="/app/hjaelp" className="underline underline-offset-2">Hjælp</Link>
            <span title={process.env.APP_COMMIT ? `Build ${process.env.APP_COMMIT}` : undefined} className="tabular-nums">{process.env.APP_VERSION}</span>
          </span>
        </div>
      </footer>
      <BottomTabs items={MAIN} />
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
