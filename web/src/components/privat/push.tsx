"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { useT } from "@/i18n/client";
import { alreadyAsked, currentPushState, disablePush, enablePush, type PushState } from "@/lib/privat/push";
import { Bag } from "@/components/lego";
import { Pill, Sim } from "./bits";
import { usePrivat } from "./store";

/** «Tryk Del → Føj til hjemmeskærm»: on iPhone, web push only works from the home-screen app. */
export function HomeScreenGuide() {
  const t = useT("privat");
  return (
    <div className="flex flex-col gap-3 rounded-[14px] border-[1.5px] border-ink bg-panel p-3" data-testid="ios-guide">
      <p className="m-0 font-semibold text-[15px]">{t("push.iosTitle")}</p>
      <div className="flex gap-3 items-start">
        <svg width="86" height="150" viewBox="0 0 86 150" aria-hidden className="shrink-0">
          <rect x="2" y="2" width="82" height="146" rx="14" fill="#fff" stroke="#14213D" strokeWidth="3" />
          <rect x="10" y="16" width="66" height="104" rx="4" className="fill-panel" />
          <rect x="16" y="24" width="20" height="20" rx="5" className="fill-accent" />
          <rect x="10" y="124" width="66" height="18" rx="3" fill="#fff" stroke="#D6DEEA" strokeWidth="1.5" />
          <g transform="translate(36 125)" fill="none" className="stroke-accent" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="6" width="10" height="9" rx="1.5" /><path d="M7 1v9M4 4l3-3 3 3" />
          </g>
          <circle cx="43" cy="133" r="12" fill="none" stroke="#FFCF3F" strokeWidth="3" />
        </svg>
        <ol className="m-0 p-0 list-none flex flex-col gap-2.5">
          <li className="flex items-start gap-2.5"><Bag n={1} size={30} /><span className="text-[14px] pt-1">{t("push.iosStep1")}</span></li>
          <li className="flex items-start gap-2.5"><Bag n={2} size={30} /><span className="text-[14px] pt-1">{t("push.iosStep2")}</span></li>
        </ol>
      </div>
      <p className="m-0 text-[12px] text-muted">{t("push.iosNote")}</p>
    </div>
  );
}

/** Ask for notifications at the right moment. `moment` = the first reminder, the first call approval, or Konto. */
export function PushPrompt({ moment }: { moment: "reminder" | "call" | "account" }) {
  const t = useT("privat");
  const { api, simulated, refresh } = usePrivat();
  const [state, setState] = useState<PushState | null>(null);
  const [skip, setSkip] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    currentPushState().then((s) => { if (alive) setState(s); });
    if (moment !== "account" && alreadyAsked()) setSkip(true);
    return () => { alive = false; };
  }, [moment]);
  if (!state || (skip && state !== "on")) return null;
  const on = async () => {
    setBusy(true); setNote("");
    try { setState(await enablePush(api)); await refresh(); } catch { setNote(t("push.failed")); } finally { setBusy(false); }
  };
  const off = async () => { setBusy(true); await disablePush(api); setState("default"); setBusy(false); await refresh(); };
  const test = async () => { setBusy(true); try { const r = await api.pushTest(); setNote(t("push.testSent", { n: r.sent })); } catch { setNote(t("push.failed")); } finally { setBusy(false); } };
  const box = moment === "account" ? "flex flex-col gap-2.5" : "flex flex-col gap-2 border-t-[1.5px] border-line pt-2.5";
  return (
    <div className={box} data-testid={`push-${moment}`}>
      {state === "ios-home" && <HomeScreenGuide />}
      {state === "default" && (
        <>
          <p className="m-0 text-[14px] text-ink-soft">{moment === "call" ? t("push.askCall") : moment === "reminder" ? t("push.askReminder") : t("push.askAccount")}</p>
          <Button variant="outline" className="self-start border-2" onClick={on} disabled={busy}>{t("push.enable")}</Button>
        </>
      )}
      {state === "on" && (
        <>
          <p className="m-0 text-[14px] flex items-center gap-2 flex-wrap">{simulated && <Sim />}<Pill tone="ok">{t("push.on")}</Pill></p>
          {moment === "account" && (
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" className="border-2" onClick={test} disabled={busy}>{t("push.test")}</Button>
              <Button variant="outline" onClick={off} disabled={busy}>{t("push.disable")}</Button>
            </div>
          )}
        </>
      )}
      {state === "denied" && <p className="m-0 text-[14px] text-ink-soft">{t("push.denied")}</p>}
      {state === "unsupported" && <p className="m-0 text-[14px] text-ink-soft">{t("push.unsupported")}</p>}
      {note && <p role="status" className="m-0 text-[13px] text-ink-soft">{note}</p>}
    </div>
  );
}
