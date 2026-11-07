"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useT } from "@/i18n/client";
import { isStandalone } from "@/lib/install";

/** Marks <html data-standalone="1"> when the page runs as an installed app on an /app or /privat route, so globals.css
 *  can drop the public header/footer (there is no browser chrome to fall back on, the app shell is the chrome). */
export function StandaloneChrome() {
  const path = usePathname();
  useEffect(() => {
    const on = isStandalone() && (path === "/app" || path.startsWith("/app/") || path === "/privat" || path.startsWith("/privat/"));
    const root = document.documentElement;
    if (on) root.setAttribute("data-standalone", "1"); else root.removeAttribute("data-standalone");
  }, [path]);
  return null;
}

export function useStandalone(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia?.("(display-mode: standalone)");
    const sync = () => setOn(isStandalone());
    sync();
    mq?.addEventListener("change", sync);
    return () => mq?.removeEventListener("change", sync);
  }, []);
  return on;
}

/** The back affordance of the installed app: on a detail page (anything deeper than the audience's main pages) a 44 px
 *  «Tilbage» at the left of the header. Goes back in history when there is one, else to the parent page. Browsers
 *  have their own back button, so it only shows in standalone mode. */
export function StandaloneBack({ roots, className = "" }: { roots: string[]; className?: string }) {
  const t = useT("common");
  const path = usePathname();
  const router = useRouter();
  const standalone = useStandalone();
  if (!standalone) return null;
  const detail = !roots.includes(path) && roots.some((r) => path.startsWith(r + "/"));
  if (!detail) return null;
  const parent = path.replace(/\/[^/]+$/, "") || "/";
  const back = () => { if (window.history.length > 1) router.back(); else router.push(parent); };
  return (
    <button type="button" onClick={back} aria-label={t("pwa.back")} data-testid="standalone-back"
      className={`inline-flex items-center justify-center w-11 h-11 -ml-2 rounded-full text-ink hover:bg-panel shrink-0 ${className}`}>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M15 5l-7 7 7 7" /></svg>
    </button>
  );
}
