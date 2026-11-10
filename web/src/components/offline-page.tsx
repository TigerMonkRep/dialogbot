import Link from "next/link";
import { getT } from "@/i18n/server";
import { Icon, LogoMark } from "@/components/ui";
import { Ico } from "@/components/privat/icons";
import { MAIN } from "@/components/shell";
import { OfflineActions } from "./offline-page.client";

/** «Ingen forbindelse» – the page the service worker shows for a navigation without net (precached on install).
 *  Static and self-contained (no backend, no session): standalone header with the «Offline» pill, the Trin-gul step
 *  mark, the copy from the app-shell mockup, «Prøv igen», and the audience's tabs. */
export async function OfflinePage({ audience }: { audience: "erhverv" | "privat" }) {
  const t = await getT("common");
  const privat = audience === "privat";
  return (
    <div data-theme={privat ? "privat" : undefined} className="min-h-dvh flex flex-col bg-panel text-ink app-type">
      <header className="flex-none flex items-center gap-2.5 px-4 min-h-16 border-b-2 border-ink bg-paper pt-safe">
        <LogoMark size={32} />
        <span className="font-display font-extrabold text-[20px] tracking-[-0.3px]">Dialogbot</span>
        {privat && <span className="text-[11px] font-bold tracking-[0.08em] uppercase text-accent border-[1.5px] border-accent rounded-full px-2 py-0.5">Privat</span>}
        <span className="ml-auto inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] border-ink bg-panel text-[11px] font-semibold uppercase tracking-[0.12em]" role="status">{t("pwa.offlinePill")}</span>
      </header>
      <main id="main" className="flex-1 flex flex-col items-center text-center gap-4 px-6 py-10 max-w-[480px] w-full mx-auto">
        <span className="w-[72px] h-[72px] rounded-[20px] bg-highlight border-2 border-ink inline-flex items-center justify-center" aria-hidden>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8.5a15 15 0 0 1 20 0M5.5 12a10 10 0 0 1 13 0M9 15.5a5 5 0 0 1 6 0M12 19h.01" /><path d="M3 3l18 18" /></svg>
        </span>
        <h1 className="m-0 font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.02em]">{t("pwa.offlineTitle")}</h1>
        <p className="m-0 text-[15px] leading-normal text-ink-soft">{t(privat ? "pwa.offlinePrivat" : "pwa.offlineErhverv")}</p>
        <OfflineActions retry={t("pwa.retry")} />
        <p className="m-0 text-[13px] text-muted">{t("pwa.offlineNote")}</p>
      </main>
      {privat ? <PrivatTabs /> : <ErhvervTabs />}
    </div>
  );
}

async function ErhvervTabs() {
  const t = await getT("app");
  return (
    <nav aria-label={t("shell.pages")} className="sm:hidden flex-none bg-paper border-t-2 border-ink pb-safe">
      <ul className="grid grid-cols-4 m-0 p-0 list-none">
        {MAIN.map((it) => (
          <li key={it.href} className="min-w-0">
            <Link href={it.href} className="flex flex-col items-center justify-center gap-0.5 min-h-[60px] px-1 text-[12px] leading-tight font-semibold text-ink no-underline">
              <span className="inline-flex items-center justify-center w-12 h-7 rounded-full"><Icon name={it.icon} size={20} /></span>
              <span className="block max-w-full truncate">{it.short ? t(it.short) : t(it.label)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

async function PrivatTabs() {
  const t = await getT("privat");
  const tabs: [string, string, string][] = [["/privat/dag", "nav.day", "home"], ["/privat/opgaver", "tabs.tasks", "list"], ["/privat/apps", "apps.tab", "grid"], ["/privat/folk", "nav.people", "users"], ["/privat/konto", "nav.account", "user"]];
  return (
    <nav aria-label={t("tabs.label")} className="xl:hidden flex-none flex border-t-2 border-ink bg-paper pb-safe">
      {tabs.map(([href, label, icon]) => (
        <Link key={href} href={href} className="flex-1 min-w-0 min-h-16 flex flex-col items-center justify-center gap-1 text-[11px] font-semibold text-muted no-underline">
          <span className="inline-flex items-center justify-center w-9 h-7 rounded-full"><Ico name={icon} size={20} /></span>
          <span className="max-w-full truncate px-1">{t(label)}</span>
        </Link>
      ))}
    </nav>
  );
}
