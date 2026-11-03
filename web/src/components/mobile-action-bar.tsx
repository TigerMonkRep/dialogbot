"use client";
import { useEffect, useRef } from "react";

/** The page's main action (fx «Videre til trin 3») pinned to the bottom of a phone; an ordinary row from sm.
 *  It publishes its height as --action-bar-h on <html>, so the page can leave room for it (`pb-action-bar`) and the
 *  floating assistant button can sit just above it instead of on top of it. */
export function MobileActionBar({ className = "", children }: { className?: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const root = document.documentElement;
    const set = () => {
      const fixed = getComputedStyle(el).position === "fixed";
      root.style.setProperty("--action-bar-h", fixed ? `${Math.ceil(el.getBoundingClientRect().height)}px` : "0px");
    };
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    window.addEventListener("resize", set);
    return () => { ro.disconnect(); window.removeEventListener("resize", set); root.style.removeProperty("--action-bar-h"); };
  }, []);
  return (
    <div ref={ref} className={`fixed sm:static inset-x-0 bottom-0 z-20 bg-paper sm:bg-transparent border-t-2 sm:border-0 border-ink px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:p-0 flex gap-3 ${className}`}>
      {children}
    </div>
  );
}
