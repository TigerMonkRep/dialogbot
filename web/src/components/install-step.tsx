"use client";
import { useEffect, useState } from "react";
import { useT } from "@/i18n/client";
import { InstallApp } from "@/components/install-app";
import { isStandalone } from "@/lib/install";

const SEEN_KEY: Record<"erhverv" | "privat", string> = { erhverv: "dialogbot-erhverv-install-seen", privat: "dialogbot-privat-install-seen" };

/** The install moment as a byggevejledning step: number → headline → «Du skal bruge» → text → one button (InstallApp,
 *  which does the right thing per phone). Used after the demo call (/proev, /start/klar) and – once-dismissible – on
 *  the first open of the app (/app, /privat/dag). Never on first paint of a landing page. */
export function InstallStep({ audience, step, enableNotifications, onDismiss, className = "" }: {
  audience: "erhverv" | "privat";
  /** «Trin 4 af 4» – or «Sidste trin» without it. */
  step?: { n: number; total: number };
  enableNotifications?: () => Promise<unknown>;
  /** With it the card gets «Ikke nu» (the once-dismissible banner). */
  onDismiss?: () => void;
  className?: string;
}) {
  const t = useT("common");
  return (
    <section aria-labelledby="install-step-h" data-testid="install-step" className={`rounded-[20px] border-2 border-ink bg-paper p-5 flex flex-col gap-3.5 ${className}`}>
      <div className="flex items-center gap-3.5">
        <span className="w-14 h-14 rounded-[14px] bg-highlight inline-flex items-center justify-center font-display font-extrabold text-[30px] text-ink shrink-0" aria-hidden>{step ? step.n : "✓"}</span>
        <div className="min-w-0">
          <span className="eyebrow block">{step ? t("pwa.stepOf", { n: step.n, total: step.total }) : t("pwa.lastStep")}</span>
          <h2 id="install-step-h" className="m-0 font-display font-bold text-[20px] leading-tight text-ink">{t("pwa.installStepTitle")}</h2>
        </div>
      </div>
      <div className="rounded-[14px] border-[1.5px] border-ink bg-paper px-3.5 py-3 flex flex-col gap-2">
        <span className="eyebrow">{t("pwa.needs")}</span>
        <div className="flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-[10px] bg-panel text-[14px]"><b className="font-display font-extrabold">1×</b> {t("pwa.needPhone")}</span>
          <span className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-[10px] bg-panel text-[14px]"><b className="font-display font-extrabold">1×</b> {t("pwa.needBrowser")}</span>
        </div>
      </div>
      <p className="m-0 text-[15px] leading-normal text-ink-soft">{t(audience === "privat" ? "pwa.installStepTextPrivat" : "pwa.installStepTextErhverv")}</p>
      <InstallApp audience={audience} enableNotifications={enableNotifications} compact />
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="self-start inline-flex items-center min-h-[44px] px-1 text-[14px] font-semibold text-muted underline underline-offset-2 hover:text-ink">{t("pwa.dismiss")}</button>
      )}
    </section>
  );
}

/** The once-dismissible banner for the first open of the app: hidden in the installed app and after «Ikke nu»
 *  (localStorage). The person is already past the login, so the home screen is the obvious next step. */
export function InstallBanner({ audience, enableNotifications, className = "" }: { audience: "erhverv" | "privat"; enableNotifications?: () => Promise<unknown>; className?: string }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (isStandalone()) return;
    try { if (localStorage.getItem(SEEN_KEY[audience]) === "1") return; } catch { return; }
    setShow(true);
  }, [audience]);
  if (!show) return null;
  const dismiss = () => { try { localStorage.setItem(SEEN_KEY[audience], "1"); } catch { /* optional */ } setShow(false); };
  return <InstallStep audience={audience} enableNotifications={enableNotifications} onDismiss={dismiss} className={className} />;
}
