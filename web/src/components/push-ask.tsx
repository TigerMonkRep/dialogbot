"use client";
import { useEffect, useState } from "react";
import { useT } from "@/i18n/client";
import { alreadyAsked, currentPushState, disablePush, enablePush, markAsked, type PushState } from "@/lib/push";

/** «Skal jeg give dig besked på telefonen?» – the permission card on the first visit to Opkald (never on login).
 *  One tap asks the browser; «Ikke nu» hides it for good on this device (Konto can still turn notifications on).
 *  Shown only when the browser can do push, nothing has been decided yet, and – on iPhone – the app is on the home
 *  screen (otherwise the install step is the right first move). */
export function PushAsk({ workspaceId }: { workspaceId: string }) {
  const t = useT("common");
  const [state, setState] = useState<PushState | "hidden">("hidden");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (alreadyAsked()) return;
    currentPushState().then((s) => { if (s === "default") setState("default"); });
  }, []);
  if (state === "hidden") return null;
  const enable = async () => {
    setBusy(true); setError(false);
    try { setState(await enablePush(workspaceId)); } catch { setError(true); setState("default"); } finally { setBusy(false); }
  };
  const later = () => { markAsked(); setState("hidden"); };
  if (state === "on") {
    return (
      <p role="status" className="m-0 flex items-center gap-2 rounded-[14px] border-2 border-success bg-success-soft px-3.5 py-2.5 text-[14px] font-semibold text-success" data-testid="push-on">
        <span className="inline-flex w-5 h-5 rounded-full bg-success text-white items-center justify-center text-[12px]" aria-hidden>✓</span>{t("pwa.pushOn")}
        <button type="button" onClick={() => setState("hidden")} className="ml-auto underline font-semibold text-success min-h-[44px]">{t("install.close")}</button>
      </p>
    );
  }
  return (
    <section aria-labelledby="push-ask-h" data-testid="push-ask" className="rounded-[14px] border-[1.5px] border-ink bg-paper p-3.5 flex flex-col gap-2.5">
      <span className="eyebrow">{t("pwa.pushEyebrow")}</span>
      <div className="flex gap-3.5 items-start">
        <span className="w-10 h-10 rounded-[10px] bg-accent text-white inline-flex items-center justify-center shrink-0" aria-hidden>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4" /></svg>
        </span>
        <div className="min-w-0">
          <h2 id="push-ask-h" className="m-0 font-display font-bold text-[17px] leading-tight text-ink">{t("pwa.pushTitle")}</h2>
          <p className="m-0 mt-1 text-[15px] leading-normal text-ink-soft">{t("pwa.pushTextErhverv")}</p>
        </div>
      </div>
      {state === "denied" && <p className="m-0 text-[13px] text-muted" role="status">{t("pwa.pushDenied")}</p>}
      {error && <p className="m-0 text-[13px] text-danger" role="alert">{t("pwa.pushFailed")}</p>}
      <div className="flex flex-wrap gap-2">
        {state !== "denied" && (
          <button type="button" onClick={enable} disabled={busy} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-accent bg-accent text-on-accent text-[15px] font-semibold hover:bg-accent-deep disabled:opacity-60">
            {busy ? t("pwa.pushBusy") : t("pwa.pushEnable")}
          </button>
        )}
        <button type="button" onClick={later} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-ink text-[15px] font-semibold hover:bg-panel">{t("pwa.pushLater")}</button>
      </div>
    </section>
  );
}

/** Konto → «Dialogbot på din telefon»: the state of notifications on this device and the one button that flips it.
 *  This is where someone who tapped «Ikke nu» on Opkald turns them on later. */
export function PushSettings({ workspaceId }: { workspaceId: string }) {
  const t = useT("common");
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => { currentPushState().then(setState); }, []);
  if (!state || state === "unsupported") return null;
  const flip = async () => {
    setBusy(true); setError(false);
    try {
      if (state === "on") { await disablePush(); setState("default"); }
      else setState(await enablePush(workspaceId));
    } catch { setError(true); } finally { setBusy(false); }
  };
  const label = state === "on" ? t("pwa.pushOn") : state === "denied" ? t("pwa.pushDenied") : state === "ios-home" ? t("pwa.pushIosHome") : t("pwa.pushOff");
  return (
    <div className="flex flex-col gap-2" data-testid="push-settings" data-push-state={state}>
      <p className="m-0 text-[14px] text-ink-soft">{label}</p>
      {error && <p className="m-0 text-[13px] text-danger" role="alert">{t("pwa.pushFailed")}</p>}
      {(state === "on" || state === "default") && (
        <button type="button" onClick={flip} disabled={busy} className={`self-start inline-flex items-center justify-center min-h-[44px] px-4 rounded-full border-2 border-ink text-[14px] font-semibold ${state === "on" ? "bg-paper text-ink hover:bg-panel" : "bg-accent text-on-accent hover:bg-accent-deep"} disabled:opacity-60`}>
          {busy ? t("pwa.pushBusy") : state === "on" ? t("pwa.pushDisable") : t("pwa.pushEnable")}
        </button>
      )}
    </div>
  );
}
