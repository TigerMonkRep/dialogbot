"use client";
import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui";
import { useT } from "@/i18n/client";
import { AccountPane } from "./account";
import { AddonsPage } from "./addons";
import { PeoplePage } from "./people";
import { Sim } from "./bits";
import { ChatPane } from "./chat";
import { DayPane } from "./day";
import { Ico } from "./icons";
import { Sheets } from "./sheets";
import { registerSw } from "@/lib/privat/push";
import { PrivatProvider, initials, usePrivat, type Screen, type Session } from "./store";
import { TaskDetail, TasksPane } from "./tasks";

export function PrivatApp({ session }: { session: Session }) {
  return (
    <PrivatProvider session={session}>
      <Shell />
    </PrivatProvider>
  );
}

function Shell() {
  // The push service worker (public/sw.js) is registered for the /privat pages; asking for permission comes later.
  useEffect(() => { void registerSw(); }, []);
  const t = useT("privat");
  const { screen, routeTaskId, isDesk, busy, mode } = usePrivat();
  // On a wide screen the right column shows Opgaver unless the route asks for a task, Konto or Tilføjelser.
  const right: Screen = screen === "day" || screen === "chat" ? "tasks" : screen;
  const show = (s: "day" | "chat" | "right") => (s === "right" ? ["tasks", "task", "account", "addons", "people"].includes(screen) : screen === s);
  const pane = (s: "day" | "chat" | "right") => `${show(s) ? "flex" : "hidden"} xl:flex`;
  void isDesk;
  return (
    <div className="h-dvh flex flex-col bg-paper text-ink overflow-hidden app-type" data-busy={busy || mode === "loading" ? "true" : "false"}>
      <a href="#privat-main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">{t("header.skip")}</a>
      <Header />
      <AccountNotice />
      <div id="privat-main" className="flex-1 min-h-0 relative xl:grid xl:grid-cols-[380px_minmax(0,1fr)_460px]">
        <section aria-label={t("day.title")} className={`${pane("day")} flex-col absolute inset-0 xl:static overflow-y-auto bg-paper xl:bg-panel xl:border-r-2 xl:border-ink`}>
          <div className="w-full max-w-[720px] mx-auto xl:max-w-none"><DayPane /></div>
        </section>
        <section aria-label={t("chat.label")} className={`${pane("chat")} flex-col absolute inset-0 xl:static min-h-0 xl:border-r-2 xl:border-ink`}>
          <div className="flex-1 min-h-0 flex flex-col w-full max-w-[720px] mx-auto xl:max-w-none"><ChatPane /></div>
        </section>
        <section aria-label={t(`header.right.${right}`)} className={`${pane("right")} flex-col absolute inset-0 xl:static overflow-y-auto`}>
          <div className="w-full max-w-[720px] mx-auto xl:max-w-none">
            <Suspense>
              {right === "tasks" && <TasksPane />}
              {right === "task" && routeTaskId && <TaskDetail key={routeTaskId} id={routeTaskId} />}
              {right === "account" && <AccountPane />}
              {right === "addons" && <AddonsPage />}
              {right === "people" && <PeoplePage />}
            </Suspense>
          </div>
        </section>
      </div>
      <Tabs />
      <Sheets />
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

function Header() {
  const t = useT("privat");
  const { balance, go, mode, simulated, loggedIn, session } = usePrivat();
  const free = balance ? Math.max(0, balance.free_limit - balance.free_used) : null;
  return (
    <header className="flex-none flex items-center gap-2.5 px-4 py-3 min-h-16 border-b-2 border-ink bg-paper pt-safe">
      <Link href="/privat/dag" aria-label={t("header.homeAria")} className="flex items-center gap-2.5 min-w-0 min-h-[44px]">
        <LogoMark size={36} />
        <span className="font-display font-extrabold text-[22px] tracking-[-0.3px] hidden min-[380px]:inline">Dialogbot</span>
        <span className="text-[13px] font-semibold text-muted border-[1.5px] border-line rounded-full px-2 py-0.5">{t("brand.privat")}</span>
      </Link>
      {simulated && <span className="hidden sm:inline-flex"><Sim /></span>}
      <span className="flex-1" />
      {balance && (
        <button type="button" onClick={() => go("account")} aria-label={t("header.balanceAria", { credits: balance.credits, free: free ?? 0 })}
          className="inline-flex items-center gap-2 min-h-[44px] px-3 rounded-full border-2 border-ink bg-paper text-[14px] font-semibold whitespace-nowrap hover:bg-panel" data-testid="balance-chip">
          <Ico name="coin" size={18} />
          <span>{t("header.credits", { n: balance.credits })}</span>
          <span className="text-muted font-medium hidden min-[400px]:inline">· {t("header.free", { n: free ?? 0 })}</span>
        </button>
      )}
      {loggedIn && mode !== "loading" ? <AccountMenu session={session} /> : mode === "demo" ? (
        <Link href={`/login?next=${encodeURIComponent("/privat/dag")}`} className="hidden sm:inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink font-semibold text-[15px] hover:bg-panel">{t("header.login")}</Link>
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
          <button type="button" role="menuitem" className={item} onClick={() => { setOpen(false); go("addons"); }}><Ico name="puzzle" size={18} />{t("header.addons")}</button>
          <button type="button" role="menuitem" className={item} onClick={() => { setOpen(false); go("people"); }}><Ico name="users" size={18} />{t("header.people")}</button>
          <button type="button" role="menuitem" className={item} onClick={logout}><Ico name="arrow" size={18} />{t("header.logout")}</button>
        </div>
      )}
    </div>
  );
}

function Tabs() {
  const t = useT("privat");
  const { screen } = usePrivat();
  const active = screen === "task" ? "tasks" : screen === "addons" || screen === "people" ? "account" : screen;
  const tabs: [Screen, string, string][] = [["day", "/privat/dag", "tabs.day"], ["chat", "/privat/samtale", "tabs.chat"], ["tasks", "/privat/opgaver", "tabs.tasks"], ["account", "/privat/konto", "tabs.account"]];
  return (
    <nav aria-label={t("tabs.label")} className="xl:hidden flex-none flex border-t-2 border-ink bg-paper pb-safe">
      {tabs.map(([k, href, label]) => (
        <Link key={k} href={href} aria-current={active === k ? "page" : undefined}
          className={`flex-1 min-w-0 min-h-16 flex flex-col items-center justify-center gap-1 text-[12px] font-semibold ${active === k ? "text-ink" : "text-muted"}`}>
          <span className={`w-7 h-1 rounded-sm ${active === k ? "bg-ink" : "bg-transparent"}`} aria-hidden />
          <span className="max-w-full truncate px-1">{t(label)}</span>
        </Link>
      ))}
    </nav>
  );
}
