"use client";
import { useEffect, useState } from "react";
import { useT } from "@/i18n/client";
import { Button } from "@/components/ui";

/** Error boundary body for the pages behind the login (app/app/error.tsx, app/opsaetning/error.tsx): in the visitor's
 *  language instead of Next's English «This page couldn’t load», with «Prøv igen» and «Log ind igen» (back to the same
 *  page afterwards). A dead session normally never gets here – api.server redirects to /login?expired=1 (F-E2A-04-A02). */
export function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useT("common");
  const [next, setNext] = useState("/app");
  useEffect(() => { setNext(window.location.pathname + window.location.search); }, []);
  return (
    <main id="main" className="min-h-[60dvh] flex flex-col items-center justify-center text-center gap-4 px-6 py-10 max-w-[520px] mx-auto">
      <h1 className="m-0 font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.02em] text-ink">{t("pageError.title")}</h1>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{t("pageError.text")}</p>
      <div className="flex flex-wrap gap-3 justify-center">
        <Button type="button" icon="refresh" onClick={() => reset()}>{t("pageError.retry")}</Button>
        <a className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-ink text-[14px] font-semibold"
          href={`/login?expired=1&next=${encodeURIComponent(next)}`}>{t("pageError.login")}</a>
      </div>
      {error.digest && <p className="m-0 text-[12px] text-muted">{t("pageError.reference")}: {error.digest}</p>}
    </main>
  );
}
