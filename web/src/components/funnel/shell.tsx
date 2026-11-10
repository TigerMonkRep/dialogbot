"use client";
import Link from "next/link";
import { useT } from "@/i18n/client";
import { Bag } from "@/components/lego";
import { LogoMark } from "@/components/ui";
import { Ico } from "@/components/privat/icons";
import { useFunnel } from "./provider";

/** The frame of every funnel screen: the audience bar at the very top (server-rendered, from the provider), a thin
 *  header with back, the logo and «Trin 3 af 7» with the yellow step squares (Byggevejledning: done = ink with a
 *  check, here = Trin-gul, ahead = outlined), then one centred column. No menu, no phone number, no chat widget –
 *  nothing that leads away from the question. `step` overrides the URL step (the reveal page has none). */
export function FunnelShell({ step: forced, children, brand = "Dialogbot", home }: { step?: number; children: React.ReactNode; brand?: string; home?: string }) {
  const t = useT("site.funnel.shell");
  const f = useFunnel();
  const step = forced ?? f.step;
  const total = f.total;
  const homeHref = home ?? (f.kind === "privat" ? "/privat" : "/");
  return (
    <div className="min-h-dvh bg-paper text-ink flex flex-col app-type overflow-x-clip" data-funnel={f.kind} data-step={step}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-paper">{t("skip")}</a>
      <header className="border-b-2 border-ink bg-white">
        <div className="max-w-[720px] mx-auto px-2 sm:px-4 min-h-14 sm:min-h-16 flex items-center gap-1 sm:gap-2">
          <button type="button" onClick={f.back} aria-label={t("back")} className="w-11 h-11 rounded-xl inline-flex items-center justify-center text-ink hover:bg-panel cursor-pointer">
            <Ico name="arrow" size={22} className="-scale-x-100" stroke={2.6} />
          </button>
          <Link href={homeHref} className="inline-flex items-center gap-2 min-h-11 text-ink no-underline" aria-label={`${brand} – ${t("home")}`}>
            <LogoMark size={30} />
            <span className="font-display font-extrabold text-[18px] tracking-[-0.3px] hidden min-[360px]:inline">{brand}</span>
          </Link>
          {step > 0 && (
            <div className="ml-auto flex items-center gap-2 sm:gap-3" aria-label={t("stepOf", { n: step, total })}>
              <ol className="hidden sm:flex items-center gap-1" aria-hidden>
                {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
                  <li key={n}><Bag n={n} size={26} tone={n < step ? "done" : n === step ? "active" : "idle"} /></li>
                ))}
              </ol>
              <span className="sm:hidden"><Bag n={step} size={30} tone="active" /></span>
              <span className="text-[13px] sm:text-[14px] font-semibold text-ink whitespace-nowrap">{t("stepOf", { n: step, total })}</span>
            </div>
          )}
          {step === 0 && f.simulated && <span className="ml-auto"><Sim /></span>}
        </div>
      </header>
      <main id="main" className="flex-1 w-full max-w-[640px] mx-auto px-4 sm:px-6 pt-6 pb-10 sm:pt-10 flex flex-col gap-6">
        {children}
      </main>
      <footer className="border-t-2 border-ink bg-white">
        <div className="max-w-[720px] mx-auto px-4 min-h-12 flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px] text-muted">
          <span>{t("footer")}</span>
          <Link href="/privatliv" className="text-ink no-underline hover:underline inline-flex items-center min-h-11">{t("privacy")}</Link>
          {f.simulated && step > 0 && <span className="ml-auto"><Sim /></span>}
        </div>
      </footer>
    </div>
  );
}

/** «Simuleret»: fake mode – nothing was built, sent or called. */
export function Sim() {
  const t = useT("site.funnel.shell");
  return <span className="inline-flex items-center min-h-[22px] px-2 rounded-full border-[1.5px] border-dashed border-ink bg-panel text-[11px] font-semibold tracking-[0.04em] uppercase text-ink whitespace-nowrap">{t("simulated")}</span>;
}
