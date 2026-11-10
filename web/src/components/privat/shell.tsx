"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui";
import { AssistantNameProvider, useT } from "@/i18n/client";
import { AccountPane } from "./account";
import { AppPage, MyAppsPage, ShopItemPage, ShopPage, Toast } from "./apps";
import { PeoplePage } from "./people";
import { Sim } from "./bits";
import { ChatPane } from "./chat";
import { DayPage } from "./day";
import { Ico } from "./icons";
import { Sheets } from "./sheets";
import { InstallCapture } from "@/components/install-app";
import { SwUpdate } from "@/components/sw-update";
import { clearSwPages } from "@/lib/sw-register";
import { StandaloneBack, StandaloneChrome } from "@/components/standalone";
import { APP_SCREENS, PrivatProvider, initials, usePlan, usePrivat, type Screen, type Session } from "./store";
import { TaskDetail, TasksPane } from "./tasks";

export function PrivatApp({ session }: { session: Session }) {
  return (
    <PrivatProvider session={session}>
      <Named><Shell /></Named>
    </PrivatProvider>
  );
}

/** The texts say the name the user gave the assistant (Konto → «Assistentens navn», or the first signup screen). */
function Named({ children }: { children: React.ReactNode }) {
  const { balance } = usePrivat();
  return <AssistantNameProvider name={balance?.assistant_name} pronoun={balance?.assistant_pronoun}>{children}</AssistantNameProvider>;
}

function Shell() {
  // public/sw.js (push + app shell, scope /privat/) is registered by <SwUpdate>; asking for push permission comes later.
  const t = useT("privat");
  const { screen, routeTaskId, routeAppKey, busy, mode } = usePrivat();
  const appsScreen = APP_SCREENS.includes(screen);
  // Min dag is its own page. Every other screen keeps the conversation on a wide screen: Samtale on the left and
  // Opgaver (or the task, Konto, Butikken, Folk) on the right; on a phone one of them fills the screen.
  const right: Screen = screen === "chat" ? "tasks" : screen;
  const rightLabel = right === "store" || right === "addons" ? t("nav.store") : t(`header.right.${right}`);
  const pane = (on: boolean) => `${on ? "flex" : "hidden"} xl:flex`;
  return (
    <div className="h-dvh flex flex-col bg-paper text-ink overflow-hidden app-type" data-busy={busy || mode === "loading" ? "true" : "false"}>
      <a href="#privat-main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">{t("header.skip")}</a>
      <InstallCapture />
      <Header />
      <AccountNotice />
      {screen === "day" ? (
        <main id="privat-main" aria-label={t("day.title")} className="flex-1 min-h-0 overflow-y-auto bg-paper"><DayPage /></main>
      ) : appsScreen ? (
        // Apps, Butikken and an app's page are full-width pages (like Min dag), not the panel beside the conversation.
        <main id="privat-main" aria-label={t("apps.tab")} className="flex-1 min-h-0 overflow-y-auto bg-paper">
          <Suspense>
            {screen === "apps" && <MyAppsPage />}
            {(screen === "store" || screen === "addons") && <ShopPage />}
            {screen === "storeItem" && routeAppKey && <ShopItemPage key={routeAppKey} appKey={routeAppKey} />}
            {screen === "app" && routeAppKey && <AppPage key={routeAppKey} appKey={routeAppKey} />}
          </Suspense>
        </main>
      ) : (
        <div id="privat-main" className="flex-1 min-h-0 relative xl:grid xl:grid-cols-[minmax(0,1fr)_480px]">
          <section aria-label={t("chat.label")} className={`${pane(screen === "chat")} flex-col absolute inset-0 xl:static min-h-0 xl:border-r-2 xl:border-ink`}>
            <div className="flex-1 min-h-0 flex flex-col w-full max-w-[760px] mx-auto xl:max-w-none"><ChatPane /></div>
          </section>
          <section aria-label={rightLabel} className={`${pane(screen !== "chat")} flex-col absolute inset-0 xl:static overflow-y-auto`}>
            <div className="w-full max-w-[720px] mx-auto xl:max-w-none">
              <Suspense>
                {right === "tasks" && <TasksPane />}
                {right === "task" && routeTaskId && <TaskDetail key={routeTaskId} id={routeTaskId} />}
                {right === "account" && <AccountPane />}
                {right === "people" && <PeoplePage />}
              </Suspense>
            </div>
          </section>
        </div>
      )}
      <Tabs />
      <Sheets />
      <Toast />
      <StandaloneChrome />
      <SwUpdate audience="privat" />
    </div>
  );
}

/** Errors that block the whole Privat app: e-mail not confirmed, or an operator's «Se som kunde» session. */
function AccountNotice() {
  const t = useT("privat");
  const { error } = usePrivat();
  if (error?.code === "email_not_verified") return (
    <div role="alert" className="flex-none bg-highlight border-b-2 border-ink px-4 py-2 text-[14px] text-center">
      {t("errors.emailNotVerified")} <Link href="/verify-email" className="underline font-semibold">{t("errors.verifyLink")}</Link>
    </div>
  );
  if (error?.code === "view_as_not_allowed") return <div role="alert" className="flex-none bg-ink text-paper px-4 py-2 text-[14px] text-center">{t("errors.viewAs")}</div>;
  return null;
}

/** A guest = logged in, no plan, and nothing of their own – only lists others shared (ux-audit #5, brief: «kan åbne
 *  listen, men ikke meget andet»). A guest gets Min dag · Opgaver · Konto; Apps and Folk come with a plan. */
function useGuest(): boolean {
  const { tasks, loggedIn, mode } = usePrivat();
  const p = usePlan();
  return loggedIn && mode === "real" && !p.entitled && p.status === "none" && tasks.length > 0 && tasks.every((x) => !!x.my_role && x.my_role !== "owner");
}

/** Header: logo + PRIVAT pill, the pill navigation (wide screens), the plan badge and the account avatar. */
function Header() {
  const t = useT("privat");
  const { balance, go, mode, simulated, loggedIn, session, screen } = usePrivat();
  const p = usePlan();
  const free = balance ? Math.max(0, balance.free_limit - balance.free_used) : null;
  const active: Screen = screen === "task" ? "tasks" : screen === "chat" ? "day" : APP_SCREENS.includes(screen) ? "apps" : screen;
  const guest = useGuest();
  const nav: [Screen, string][] = ([["day", "nav.day"], ["tasks", "nav.tasks"], ["apps", "apps.tab"], ["people", "nav.people"], ["account", "nav.account"]] as [Screen, string][])
    .filter(([k]) => !guest || (k !== "apps" && k !== "people"));
  // The badge: «Plus · prøveperiode, 9 dage tilbage», the plan name, or (without rights) credits and free tasks.
  const badge = p.entitled
    ? (p.status === "trial" ? t("nav.trialBadge", { plan: p.rightsName, n: p.trialDays }) : t("nav.planBadge", { plan: p.rightsName }))
    : balance ? (p.status === "none" ? t("header.noPlanBadge") : t("header.credits", { n: balance.credits })) : "";
  // Phone: as short as possible, so the logo and the PRIVAT mark are never covered (F-UX-05); the aria-label says it all.
  const badgeShort = p.entitled && p.status === "trial" ? t("nav.trialDaysShort", { n: p.trialDays }) : p.entitled ? p.rightsName : balance ? (p.status === "none" ? t("header.noPlanBadgeShort") : t("header.credits", { n: balance.credits })) : "";
  return (
    <header className="flex-none flex items-center gap-2 sm:gap-2.5 px-4 py-3 min-h-16 border-b-2 border-ink bg-paper pt-safe">
      <StandaloneBack roots={["/privat/dag", "/privat/samtale", "/privat/opgaver", "/privat/apps", "/privat/butik", "/privat/folk", "/privat/konto"]} />
      <Link href="/privat/dag" aria-label={t("header.homeAria")} className="flex items-center gap-2 shrink-0 min-h-[44px]">
        <LogoMark size={36} />
        <span className={`font-display font-extrabold text-[22px] tracking-[-0.3px] hidden ${simulated || (balance && !p.entitled) ? "min-[420px]:inline" : "min-[380px]:inline"}`}>Dialogbot</span>
        <span className="text-[11px] font-bold tracking-[0.08em] uppercase text-accent border-[1.5px] border-accent rounded-full px-2 py-0.5">{t("brand.privat")}</span>
      </Link>
      {/* Simulated data is said on every width (F-PS-07); on a phone the wordmark gives way (the mark stays). */}
      {simulated && <span className="inline-flex shrink-0"><Sim /></span>}
      <nav aria-label={t("nav.primary")} className="hidden xl:flex items-center gap-1 ml-4 p-1 rounded-full border-2 border-ink bg-paper">
        {nav.map(([k, label]) => (
          <button key={k} type="button" onClick={() => go(k)} aria-current={active === k ? "page" : undefined}
            className={`min-h-[38px] px-4 rounded-full text-[14px] font-semibold whitespace-nowrap ${active === k ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>{t(label)}</button>
        ))}
      </nav>
      <span className="flex-1" />
      {balance && (
        <button type="button" onClick={() => go("account")} aria-label={p.entitled ? t("nav.planAria", { text: badge }) : (p.status === "none" ? t("header.noPlanAria") : t("header.balanceAria", { credits: balance.credits }))}
          data-credits={balance.credits} data-free={free ?? 0} data-plan={p.plan} data-status={p.status} data-calls-left={p.callsLeft}
          className={`inline-flex items-center gap-1.5 sm:gap-2 min-h-[44px] shrink-0 px-3 sm:px-3.5 rounded-full border-2 border-ink text-[14px] font-semibold whitespace-nowrap ${p.entitled ? "bg-accent-soft hover:bg-panel-deep" : "bg-paper hover:bg-panel"}`} data-testid="balance-chip">
          <span className={`hidden min-[400px]:inline-block w-2.5 h-2.5 rounded-full border-[1.5px] border-ink ${p.entitled ? "bg-accent" : "bg-highlight"}`} aria-hidden />
          <span className="hidden sm:inline">{badge}</span><span className="sm:hidden">{badgeShort}</span>
        </button>
      )}
      {loggedIn && mode !== "loading" ? <AccountMenu session={session} /> : mode === "demo" ? (
        <Link href={`/login?next=${encodeURIComponent("/privat/dag")}`} className="hidden sm:inline-flex items-center min-h-[44px] px-4 rounded-full border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("header.login")}</Link>
      ) : null}
    </header>
  );
}

/** Avatar menu: Konto, Tilføjelser, the «Virksomhed / Privat» switch (only for people who also have a business
 *  workspace) and log out. */
function AccountMenu({ session }: { session: Session }) {
  const t = useT("privat");
  const router = useRouter();
  const { go, simulated } = usePrivat();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", down); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); };
  }, [open]);
  const toBusiness = async () => {
    if (!session.businessWsId) return;
    await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: session.businessWsId }) });
    router.push("/app");
  };
  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST", headers: { "x-requested-with": "dialogbot" } }).catch(() => {});
    await clearSwPages().catch(() => {});
    try { sessionStorage.removeItem("dialogbot-privat-fake-login"); } catch { /* ignore */ }
    window.location.href = "/privat";
  };
  const item = "flex items-center gap-2.5 w-full min-h-[44px] px-3 rounded-xl text-[15px] font-semibold text-ink hover:bg-panel text-left";
  const name = session.name ?? (simulated ? "Mette" : session.email ?? "?");
  return (
    <div className="relative shrink-0" ref={ref}>
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} aria-label={t("header.menu")} className="w-11 h-11 rounded-full inline-flex items-center justify-center">
        <span className="w-10 h-10 rounded-full bg-highlight border-2 border-ink font-display font-extrabold text-[15px] inline-flex items-center justify-center">{initials(name)}</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-[min(18rem,calc(100vw-2rem))] rounded-2xl bg-paper border-2 border-ink shadow-block-sm p-2 z-50 flex flex-col gap-1">
          <p className="m-0 px-3 py-1.5 text-[13px] text-muted [overflow-wrap:anywhere]">{session.email ?? name}</p>
          {session.businessWsId && (
            <div role="group" aria-label={t("header.switchLabel")} className="grid grid-cols-2 gap-1 p-1 rounded-full border-2 border-ink">
              <button type="button" role="menuitem" onClick={toBusiness} className="min-h-[40px] rounded-full text-[14px] font-semibold hover:bg-panel">{t("header.business")}</button>
              <span aria-current="true" className="min-h-[40px] rounded-full bg-ink text-paper text-[14px] font-semibold inline-flex items-center justify-center">{t("header.private")}</span>
            </div>
          )}
          <button type="button" role="menuitem" className={item} onClick={() => { setOpen(false); go("account"); }}><Ico name="coin" size={18} />{t("header.account")}</button>
          <button type="button" role="menuitem" className={item} onClick={() => { setOpen(false); go("people"); }}><Ico name="users" size={18} />{t("header.people")}</button>
          <button type="button" role="menuitem" className={item} onClick={logout}><Ico name="arrow" size={18} />{t("header.logout")}</button>
        </div>
      )}
    </div>
  );
}

/** Phone tabs: Min dag · Opgaver · Butikken · Folk · Konto. The conversation (/privat/samtale) counts as Min dag. */
function Tabs() {
  const t = useT("privat");
  const { screen } = usePrivat();
  const active: Screen = screen === "task" ? "tasks" : screen === "chat" ? "day" : APP_SCREENS.includes(screen) ? "apps" : screen;
  const guest = useGuest();
  const tabs = ([["day", "/privat/dag", "nav.day", "home"], ["tasks", "/privat/opgaver", "tabs.tasks", "list"], ["apps", "/privat/apps", "apps.tab", "grid"], ["people", "/privat/folk", "nav.people", "users"], ["account", "/privat/konto", "nav.account", "user"]] as [Screen, string, string, string][])
    .filter(([k]) => !guest || (k !== "apps" && k !== "people"));
  return (
    <nav aria-label={t("tabs.label")} className="xl:hidden flex-none flex border-t-2 border-ink bg-paper pb-safe">
      {tabs.map(([k, href, label, icon]) => (
        <Link key={k} href={href} aria-current={active === k ? "page" : undefined}
          className={`flex-1 min-w-0 min-h-16 flex flex-col items-center justify-center gap-1 text-[11px] font-semibold ${active === k ? "text-ink" : "text-muted"}`}>
          <span className={`inline-flex items-center justify-center w-9 h-7 rounded-full ${active === k ? "bg-accent-soft text-ink" : ""}`}><Ico name={icon} size={20} /></span>
          <span className="max-w-full truncate px-1">{t(label)}</span>
        </Link>
      ))}
    </nav>
  );
}
