"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { PHONE_DISPLAY, PHONE_TEL } from "@/lib/contact";
import { track } from "@/components/site-analytics";
import { Alert, Button } from "@/components/ui";
import { Ico } from "@/components/privat/icons";
import { FunnelShell, FunnelState, Question, useFunnel } from "@/components/funnel";
import { useFunnelError } from "@/components/funnel/parts";
import { isDone, type Call } from "@/lib/funnel/api";
import { InstallStep } from "@/components/install-step";

const POLL_MS = 3000;
const MAX_WAIT_MS = 150_000;

/** «Hun ringer nu til 12 34 56 78»: the number comes from the gate (kept in sessionStorage), and
 *  GET /funnel/drafts/{id}/reveal is polled until the call has ended – then its summary is shown. Peter rings at once,
 *  day and night (Fürster 12/11): there are no calling hours to show and no queue. «Gør hende til jeres» leads into the setup guide with the draft's company already in place. «Hør det igen»
 *  only when the API gives an audio URL. */
export function Klar() {
  const t = useT("site.funnel.erhverv.klar");
  const say = useFunnelError();
  const f = useFunnel();
  const [call, setCall] = useState<Call | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [waitedOut, setWaitedOut] = useState(false);
  const started = useRef(Date.now());
  const reported = useRef(false);
  const draft = f.draft;
  const phone = f.gate?.phone_display ?? null;

  useEffect(() => {
    if (!draft) return;
    let alive = true;
    const tick = async () => {
      try {
        const r = await f.api.reveal(draft.id);
        if (!alive) return;
        setErr(null);
        setCall(r.call);
        // No call was placed (already called today, not open yet …): stop polling, say so.
        if (!r.call && r.call_problem) { setProblem(r.call_problem); return; }
        setProblem(null);
        if (isDone(r.call)) {
          if (!reported.current) { reported.current = true; track("funnel_call_done", { kind: "erhverv", step: 8, hook: f.hook, industry: draft.answers.industry ?? null, status: r.call?.status }); }
          return;
        }
      } catch (e) {
        if (!alive) return;
        setErr(e as ApiError);
        if ((e as ApiError).status === 401) return;
      }
      if (Date.now() - started.current > MAX_WAIT_MS) { setWaitedOut(true); return; }
      h = window.setTimeout(tick, POLL_MS);
    };
    let h = window.setTimeout(tick, 0);
    return () => { alive = false; window.clearTimeout(h); };
  }, [draft, f.api, f.hook]);

  const done = isDone(call);
  const company = draft?.company?.name ?? draft?.answers.company_name ?? "";

  return (
    <FunnelShell step={0}>
      {f.status !== "ready" ? <FunnelState status={f.status === "error" ? "error" : "loading"} error={f.error} />
        : !draft ? (
          <div className="flex flex-col gap-4">
            <Question title={t("noDraft")} />
            <Link href="/start" className="self-start inline-flex items-center justify-center min-h-[48px] px-5 rounded-2xl bg-accent text-on-accent font-semibold no-underline">{t("startOver")}</Link>
          </div>
        ) : err?.status === 401 ? (
          <div className="flex flex-col gap-4">
            <Question title={t("notLoggedIn")} />
            <Link href="/login?next=%2Fstart%2Fklar" className="self-start inline-flex items-center justify-center min-h-[48px] px-5 rounded-2xl bg-accent text-on-accent font-semibold no-underline">{t("login")}</Link>
          </div>
        ) : (
          <>
            {problem ? (
              <>
                <Question title={t("noCallTitle")} />
                <section aria-label={t("statusAria")} aria-live="polite" data-call="none" className="rounded-[22px] border-2 border-ink p-5 flex flex-col gap-3 bg-white">
                  <p className="m-0 text-[16px] leading-normal text-ink" data-call-problem>{problem}</p>
                  <p className="m-0 text-[14px] text-ink-soft">{t("noCallBefore")}<a href={PHONE_TEL} className="font-semibold text-ink">{PHONE_DISPLAY}</a>{t("noCallAfter")}</p>
                </section>
              </>
            ) : (<>
            <Question title={phone ? t("title", { phone }) : t("titleNoPhone")} help={company ? t("lead", { company }) : undefined} />
            <section aria-label={t("statusAria")} aria-live="polite" data-call={done ? "done" : call?.status ?? "waiting"}
              className={`rounded-[22px] border-2 border-ink p-5 flex flex-col gap-3 ${done ? "bg-success-soft" : "bg-white"}`}>
              <div className="flex items-center gap-3">
                <span className={`w-12 h-12 rounded-full inline-flex items-center justify-center border-2 border-ink ${done ? "bg-success text-white" : "bg-highlight text-ink"}`} aria-hidden>
                  <Ico name={done ? "check" : "phone"} size={22} stroke={2.8} />
                </span>
                <div className="flex flex-col">
                  <span className="font-display font-extrabold text-[19px] text-ink">
                    {done ? t("doneTitle") : call?.status === "in_progress" ? t("inProgress") : waitedOut ? t("waitedOut") : t("waiting")}
                  </span>
                  {done && call?.duration_seconds != null && <span className="text-[13px] text-muted">{t("duration", { s: call.duration_seconds })}</span>}
                </div>
              </div>
              {done && call?.summary && <p className="m-0 text-[16px] leading-normal text-ink" data-summary>{call.summary}</p>}
              {done && !call?.summary && <p className="m-0 text-[15px] text-ink-soft">{t("noSummary")}</p>}
              {(waitedOut || call?.status === "failed" || call?.status === "no_answer") && (
                <p className="m-0 text-[14px] text-ink-soft">{t("noCallBefore")}<a href={PHONE_TEL} className="font-semibold text-ink">{PHONE_DISPLAY}</a>{t("noCallAfter")}</p>
              )}
              {err && err.status !== 401 && <Alert>{say(err)}</Alert>}
            </section>
            </>)}
            {done && <InstallStep audience="erhverv" />}
            <div className="flex flex-col sm:flex-row gap-3">
              <Link href="/opsaetning/1" className="inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-2xl bg-accent text-on-accent font-semibold text-[16px] no-underline hover:bg-accent-deep" data-make-hers>
                {t("makeHers")}<Ico name="arrow" size={18} stroke={2.8} />
              </Link>
              {done && call?.audio_url && (
                <Button variant="outline" className="min-h-[52px] rounded-2xl" onClick={() => { const a = new Audio(call.audio_url!); void a.play(); }}>{t("again")}</Button>
              )}
            </div>
            <p className="m-0 text-[13px] text-muted">{t("note")}</p>
          </>
        )}
    </FunnelShell>
  );
}
