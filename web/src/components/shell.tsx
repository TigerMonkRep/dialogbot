import Link from "next/link";
import { backend, currentWorkspaceId, isLoggedIn } from "@/lib/api.server";
import { LogoMark } from "./ui";
export { LogoMark } from "./ui";
import { cookies } from "next/headers";
import { VIEWAS_COOKIE } from "@/lib/config";
import { AssistantDock } from "./assistant";
import { getT } from "@/i18n/server";
import { Avatar, BottomTabs, TabNav, ViewAsBanner, WorkspaceChip, type NavItem } from "./shell.client";
import { InstallCapture } from "@/components/install-app";
import { SwUpdate } from "@/components/sw-update";
import { StandaloneBack, StandaloneChrome } from "@/components/standalone";

type Ws = { id: string; name: string; role: string; product_intent: string };
type Me = { display_name: string; email: string; email_verified: boolean; is_platform_operator?: boolean };
type Capability = { key: string; status: "available" | "simulated" | "not_implemented"; environment: string };

/** The four pages (Byggevejledningen: one place per question). Aftaler and Kampagner are reached from I dag.
 *  `label` is a key in the `app` namespace (translated in the shell). */
export const MAIN: NavItem[] = [
  { href: "/app", match: "/app", also: ["/app/aftaler", "/app/kampagner"], label: "nav.today", icon: "today" },
  { href: "/app/viden", match: "/app/viden", label: "nav.knowledge", short: "nav.knowledgeShort", icon: "menu_book" },
  { href: "/app/opkald", match: "/app/opkald", label: "nav.calls", icon: "call" },
  { href: "/app/ugen", match: "/app/ugen", label: "nav.week", icon: "bar_chart" },
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

async function VerifyBanner({ me }: { me: Me | null }) {
  if (!me || me.email_verified) return null;
  const t = await getT("app");
  return (
    <div className="bg-highlight text-ink border-b-2 border-ink px-4 py-2 text-center text-[14px]">
      {t("shell.verify.before")} <Link className="underline font-semibold" href="/verify-email">{t("shell.verify.link")}</Link> {t("shell.verify.after")}
    </div>
  );
}

const SkipLink = ({ label }: { label: string }) => <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">{label}</a>;

/** One shell for the whole logged-in app: header with the four pages and the avatar, bottom tabs on a phone, and the
 *  assistant «Ændr noget» (column on a wide screen, sheet behind a button elsewhere). */
async function Shell({ children }: { children: React.ReactNode }) {
  const { workspaces, me, current, env } = await shellData();
  const t = await getT("app");
  const nav = MAIN.map((it) => ({ ...it, label: t(it.label), short: it.short ? t(it.short) : undefined }));
  let viewAs: { name: string; email: string } | null = null;
  try { const raw = (await cookies()).get(VIEWAS_COOKIE)?.value; if (raw) viewAs = JSON.parse(raw); } catch { /* ignore a broken cookie */ }
  return (
    <div className="min-h-dvh bg-panel text-ink app-type flex flex-col overflow-x-clip">
      <SkipLink label={t("shell.skip")} />
      {viewAs && <ViewAsBanner who={viewAs} />}
      <header className="sticky top-0 z-30 bg-paper border-b-2 border-ink pt-safe">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 min-h-16 flex items-center gap-3 md:gap-6">
          <div className="flex items-center gap-3 min-w-0">
            <StandaloneBack roots={MAIN.flatMap((it) => [it.href, ...(it.also ?? [])]).concat(["/app/konto", "/app/indstillinger", "/app/hjaelp", "/app/leads"])} />
            <Link href="/app" className="flex items-center gap-2.5 shrink-0" aria-label={t("shell.homeAria")}>
              <LogoMark size={32} />
              <span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink">Dialogbot</span>
            </Link>
            <span className="hidden md:block"><WorkspaceChip workspaces={workspaces} current={current} plain /></span>
            {env && env !== "prod" && <span className="hidden xl:inline-flex px-2 py-0.5 rounded-full border-[1.5px] border-ink text-[11px] font-semibold uppercase tracking-[0.08em]">{env === "staging" ? t("shell.envStaging") : t("shell.envDev")}</span>}
          </div>
          <div className="hidden sm:flex items-center ml-auto"><TabNav items={nav} /></div>
          <div className="flex items-center ml-auto sm:ml-0 shrink-0"><Avatar me={me} /></div>
        </div>
        <VerifyBanner me={me} />
      </header>

      <main id="main" className="flex-grow w-full pb-[148px] sm:pb-24 xl:pb-0">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-5 md:py-7 flex gap-6 items-start">
          <div className="flex-1 min-w-0 flex flex-col">{children}</div>
          {current && <AssistantDock wsId={current.id} canChange={current.role !== "reader"} name={(me?.display_name ?? "").split(" ")[0] || undefined} />}
        </div>
      </main>

      <footer className="hidden sm:block border-t-2 border-ink bg-paper mt-8">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-4 flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
          <span className="flex items-center gap-2"><LogoMark size={18} /><span className="font-display font-extrabold text-ink">Dialogbot</span><span>·</span><span>{t("shell.tagline")}</span></span>
          <span className="flex items-center gap-4">
            {current && <span>{current.name}</span>}
            {env && env !== "prod" && <span>{t("shell.env", { env })}</span>}
            <Link href="/app/hjaelp" className="underline underline-offset-2">{t("shell.help")}</Link>
            <span title={process.env.APP_COMMIT ? `Build ${process.env.APP_COMMIT}` : undefined} className="tabular-nums">{process.env.APP_VERSION}</span>
          </span>
        </div>
      </footer>
      <BottomTabs items={nav} />
      <InstallCapture />
      <StandaloneChrome />
      {/* Registers public/sw-app.js (scope /app/) and shows «Ny version klar» when a new build is waiting. */}
      <SwUpdate audience="erhverv" />
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
