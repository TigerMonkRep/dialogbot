"use client";
import { useEffect, useState } from "react";

/** «Prøv igen» reloads the page (the service worker goes to the network; pages behind the login are never cached,
 *  F-M2-15-X23). The page also retries by itself when the browser says the net is back. */
export function OfflineActions({ retry }: { retry: string }) {
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const online = () => window.location.reload();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, []);
  return (
    <div className="w-full flex flex-col gap-2.5">
      <button type="button" disabled={busy} onClick={() => { setBusy(true); window.location.reload(); }}
        className="w-full inline-flex items-center justify-center min-h-[52px] px-5 rounded-[14px] border-2 border-accent bg-accent text-on-accent text-[16px] font-semibold hover:bg-accent-deep disabled:opacity-60">{retry}</button>
    </div>
  );
}
