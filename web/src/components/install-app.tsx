"use client";
import { useEffect, useState } from "react";
import { useT } from "@/i18n/client";
import { Bag } from "@/components/lego";
import { captureInstallPrompt, installState, onInstallChange, platform, promptInstall, type InstallState, type Platform } from "@/lib/install";

/** Mount once per shell so the browser's install prompt is caught before anyone taps «Download app». */
export function InstallCapture() {
  useEffect(() => { captureInstallPrompt(); }, []);
  return null;
}

const BTN = "inline-flex items-center justify-center gap-2 min-h-[48px] px-5 rounded-full border-2 border-ink bg-accent text-on-accent text-[15px] font-semibold no-underline hover:bg-accent-deep disabled:opacity-50";
const BTN_OUT = "inline-flex items-center justify-center gap-2 min-h-[44px] px-4 rounded-full border-2 border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel";

/** «Download app»: one tap on Android (and desktop Chrome/Edge), a two-step guide on iPhone, where Apple allows no
 *  install API. `enableNotifications` (Privat) runs right after an accepted install; the installed app asks again on
 *  its first open if that did not go through. */
export function InstallApp({ audience, enableNotifications, compact = false }: { audience: "erhverv" | "privat"; enableNotifications?: () => Promise<unknown>; compact?: boolean }) {
  const t = useT("common");
  const [state, setState] = useState<InstallState | null>(null);
  const [os, setOs] = useState<Platform>("desktop");
  const [guide, setGuide] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    captureInstallPrompt();
    const sync = () => { setState(installState()); setOs(platform()); };
    sync();
    return onInstallChange(sync);
  }, []);
  if (!state) return null;
  const name = audience === "privat" ? "Dialogbot Privat" : "Dialogbot";
  const install = async () => {
    if (state !== "promptable") { setGuide(!guide); return; }
    setBusy(true); setNote("");
    const ok = await promptInstall();
    if (ok) {
      setNote(t("install.done", { name }));
      if (enableNotifications) { try { await enableNotifications(); setNote(t("install.doneNotify", { name })); } catch { /* asked again in the app */ } }
    }
    setBusy(false);
  };
  if (state === "installed") {
    return <p className="m-0 inline-flex items-center gap-2 text-[14px] font-semibold" data-testid="install-installed"><span className="inline-flex w-5 h-5 rounded-full bg-success text-white items-center justify-center text-[12px]" aria-hidden>✓</span>{t("install.installed", { name })}</p>;
  }
  return (
    <div className={`flex flex-col ${compact ? "gap-2" : "gap-3"}`} data-testid="install-app" data-install-state={state}>
      {!compact && <p className="m-0 text-[14px] text-ink-soft">{t(audience === "privat" ? "install.introPrivat" : "install.introErhverv")}</p>}
      <div className="flex items-center gap-3 flex-wrap">
        <button type="button" className={compact ? BTN_OUT : BTN} onClick={install} disabled={busy} aria-expanded={state === "promptable" ? undefined : guide}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 3v12M7 10l5 5 5-5M4 21h16" /></svg>
          {busy ? t("install.opening") : t("install.button")}
        </button>
        {state !== "promptable" && !guide && <span className="text-[13px] text-muted">{t(os === "ios" ? "install.hintIos" : os === "android" ? "install.hintAndroid" : "install.hintDesktop")}</span>}
      </div>
      {note && <p role="status" className="m-0 rounded-[14px] border-2 border-success bg-success-soft px-3.5 py-2.5 text-[14px] font-semibold text-success">{note}</p>}
      {guide && state === "ios" && <IosGuide privat={audience === "privat"} />}
      {guide && state === "manual" && (
        <div className="rounded-[14px] border-[1.5px] border-ink bg-panel p-3 flex flex-col gap-2" data-testid="install-guide-manual">
          <p className="m-0 text-[14px]">{t(os === "android" ? "install.manualAndroid" : "install.manualDesktop", { host: typeof location !== "undefined" ? location.host : "dialogbot.app", path: audience === "privat" ? "/privat" : "" })}</p>
          {enableNotifications && os !== "desktop" && <p className="m-0 text-[13px] text-muted">{t("install.thenNotify")}</p>}
        </div>
      )}
      {guide && <button type="button" className={`${BTN_OUT} self-start`} onClick={() => setGuide(false)}>{t("install.close")}</button>}
    </div>
  );
}

/** Del → «Føj til hjemmeskærm» – the only way onto an iPhone's home screen. */
function IosGuide({ privat }: { privat: boolean }) {
  const t = useT("common");
  const accent = privat ? "#E0521A" : "#2456F6";
  return (
    <div className="flex flex-col gap-3 rounded-[14px] border-[1.5px] border-ink bg-panel p-3" data-testid="install-guide-ios">
      <p className="m-0 font-semibold text-[15px]">{t("install.iosTitle")}</p>
      <div className="flex gap-3 items-start">
        <svg width="86" height="150" viewBox="0 0 86 150" aria-hidden className="shrink-0">
          <rect x="2" y="2" width="82" height="146" rx="14" fill="#fff" stroke="#14213D" strokeWidth="3" />
          <rect x="10" y="16" width="66" height="104" rx="4" fill="#EEF4FB" />
          <rect x="16" y="24" width="20" height="20" rx="5" fill={accent} />
          <rect x="10" y="124" width="66" height="18" rx="3" fill="#fff" stroke="#D6DEEA" strokeWidth="1.5" />
          <g transform="translate(36 125)" fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="6" width="10" height="9" rx="1.5" /><path d="M7 1v9M4 4l3-3 3 3" />
          </g>
          <circle cx="43" cy="133" r="12" fill="none" stroke="#FFCF3F" strokeWidth="3" />
        </svg>
        <ol className="m-0 p-0 list-none flex flex-col gap-2.5">
          <li className="flex items-start gap-2.5"><Bag n={1} size={30} /><span className="text-[14px] pt-1">{t("install.iosStep1")}</span></li>
          <li className="flex items-start gap-2.5"><Bag n={2} size={30} /><span className="text-[14px] pt-1">{t("install.iosStep2")}</span></li>
          <li className="flex items-start gap-2.5"><Bag n={3} size={30} /><span className="text-[14px] pt-1">{t(privat ? "install.iosStep3Privat" : "install.iosStep3")}</span></li>
        </ol>
      </div>
      <p className="m-0 text-[12px] text-muted">{t("install.iosNote")}</p>
    </div>
  );
}
