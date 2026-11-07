"use client";
import { useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/client";
import { watchSwUpdates, type SwAudience } from "@/lib/sw-register";

/** Registers the audience's service worker and shows «Ny version klar – Opdater» once a new one is installed and
 *  waiting. One tap tells the waiting worker to take over; the page reloads when it does. The toast sits above the
 *  bottom tabs on a phone and in the corner on wider screens; it slides in only when motion is allowed. */
export function SwUpdate({ audience }: { audience: SwAudience }) {
  const t = useT("common");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const apply = useRef<(() => void) | null>(null);
  useEffect(() => watchSwUpdates(audience, (fn) => { apply.current = fn; setReady(true); }), [audience]);
  if (!ready) return null;
  const pos = audience === "privat"
    ? "bottom-[calc(76px+env(safe-area-inset-bottom,0px))] xl:bottom-6"
    : "bottom-[calc(72px+env(safe-area-inset-bottom,0px))] sm:bottom-6";
  return (
    <div role="status" aria-live="polite" data-testid="sw-update"
      className={`fixed z-[70] left-4 right-4 sm:left-auto sm:right-6 sm:w-[360px] ${pos} flex items-center gap-3 rounded-2xl border-2 border-ink bg-paper shadow-block-sm px-4 py-3 toast-in`}>
      <span className="w-9 h-9 rounded-[10px] bg-highlight border-[1.5px] border-ink inline-flex items-center justify-center shrink-0" aria-hidden>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6" /></svg>
      </span>
      <span className="flex-1 min-w-0 text-[15px] font-semibold text-ink">{t("pwa.updateReady")}</span>
      <button type="button" disabled={busy} onClick={() => { setBusy(true); apply.current?.(); }}
        className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-full border-2 border-ink bg-accent text-on-accent text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-60">
        {busy ? t("pwa.updating") : t("pwa.updateButton")}
      </button>
    </div>
  );
}
