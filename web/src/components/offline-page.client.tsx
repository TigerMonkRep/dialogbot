"use client";
import { useEffect, useState } from "react";

/** «Prøv igen» reloads (the service worker goes to the network first); «Vis det sidste, jeg så» steps back in history
 *  to the page that was open, which the worker serves from its cache. The page also retries by itself when the
 *  browser says the net is back. */
export function OfflineActions({ retry, back }: { retry: string; back: string }) {
  const [busy, setBusy] = useState(false);
  const [canBack, setCanBack] = useState(false);
  useEffect(() => {
    setCanBack(window.history.length > 1);
    const online = () => window.location.reload();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, []);
  return (
    <div className="w-full flex flex-col gap-2.5">
      <button type="button" disabled={busy} onClick={() => { setBusy(true); window.location.reload(); }}
        className="w-full inline-flex items-center justify-center min-h-[52px] px-5 rounded-[14px] border-2 border-accent bg-accent text-on-accent text-[16px] font-semibold hover:bg-accent-deep disabled:opacity-60">{retry}</button>
      {canBack && (
        <button type="button" onClick={() => window.history.back()}
          className="w-full inline-flex items-center justify-center min-h-[52px] px-5 rounded-[14px] border-2 border-ink bg-paper text-ink text-[16px] font-semibold hover:bg-panel">{back}</button>
      )}
    </div>
  );
}
