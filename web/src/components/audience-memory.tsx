"use client";

import { useEffect } from "react";

const COOKIE = "db_aud";
const ONE_YEAR = 60 * 60 * 24 * 365;

/** Remembers the door the visitor opened (Erhverv or Privat) so "/" takes them straight there next time.
 *  The proxy sets the same cookie on full page loads; this covers client-side navigations, where the proxy cannot tell
 *  a real visit from a link prefetch. Runs only when the page is actually mounted, never for a prefetched payload. */
export function AudienceMemory({ audience }: { audience: "erhverv" | "privat" }) {
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (new URLSearchParams(window.location.search).get("aud") === "reset") return;
    const current = document.cookie.split("; ").find((c) => c.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);
    if (current === audience) return;
    document.cookie = `${COOKIE}=${audience}; Path=/; Max-Age=${ONE_YEAR}; SameSite=Lax`;
  }, [audience]);
  return null;
}
