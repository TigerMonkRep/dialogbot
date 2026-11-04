"use client";
import { useEffect, useRef, useState } from "react";
import { useT } from "@/i18n/client";
import { Ico } from "@/components/privat/icons";
import { useFunnel } from "./provider";

export type RowState = "pending" | "done" | "skipped" | "default";
export type BuildRow = { key: string; label: string; state: RowState; detail?: string };

/** «Vi bygger …»: rows that go green with a check as the draft's build status comes in. The component polls
 *  GET /funnel/drafts/{id} every 1.5 s through the provider while something is still pending (and for at most
 *  `maxSeconds`); the page maps the draft's `build` to rows. States are honest: done, skipped (e.g. no website to
 *  read), default (e.g. standard opening hours) or still pending – nothing is shown as done before it is. */
export function BuildProgress({ rows, maxSeconds = 30, onSettled }: { rows: BuildRow[]; maxSeconds?: number; onSettled?: () => void }) {
  const t = useT("site.funnel.build");
  const { refresh, draft } = useFunnel();
  const pending = rows.some((r) => r.state === "pending");
  const [timedOut, setTimedOut] = useState(false);
  const settled = useRef(false);

  // Keyed on the draft id, not the draft object: every poll replaces the object, which would restart the clock.
  const draftId = draft?.id ?? null;
  useEffect(() => {
    if (!draftId) return;
    const stop = window.setTimeout(() => setTimedOut(true), maxSeconds * 1000);
    return () => window.clearTimeout(stop);
  }, [draftId, maxSeconds]);
  useEffect(() => {
    if (!pending || timedOut) return;
    const h = window.setInterval(() => { void refresh(); }, 1500);
    return () => window.clearInterval(h);
  }, [pending, timedOut, refresh]);
  useEffect(() => {
    if ((!pending || timedOut) && !settled.current) { settled.current = true; onSettled?.(); }
  }, [pending, timedOut, onSettled]);

  return (
    <ol className="m-0 p-0 list-none flex flex-col gap-2.5" aria-live="polite" data-build={pending && !timedOut ? "pending" : "settled"}>
      {rows.map((r) => {
        const done = r.state === "done";
        const soft = r.state === "skipped" || r.state === "default";
        const still = r.state === "pending";
        return (
          <li key={r.key} data-row={r.key} data-state={r.state} className={`flex items-center gap-3 rounded-2xl border-2 px-4 py-3 ${done ? "border-success bg-success-soft" : soft ? "border-ink border-dashed bg-white" : "border-ink bg-white"}`}>
            <span aria-hidden className={`w-8 h-8 shrink-0 rounded-full inline-flex items-center justify-center border-2 ${done ? "bg-success text-white border-success" : soft ? "bg-panel text-ink border-ink" : "bg-white border-ink"}`}>
              {done && <Ico name="check" size={16} stroke={3.2} />}
              {soft && <span className="block w-3 h-[2.5px] bg-ink rounded" />}
              {still && <span className="block w-3 h-3 rounded-full bg-highlight animate-pulse" />}
            </span>
            <span className="flex flex-col min-w-0 flex-1">
              <span className="font-semibold text-[15px] text-ink">{r.label}</span>
              <span className="text-[13px] text-muted">{r.detail ?? (still ? (timedOut ? t("stillPending") : t("pending")) : t(r.state))}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
