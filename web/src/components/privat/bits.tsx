"use client";
import { useT } from "@/i18n/client";
import type { Task, TaskStatus } from "@/lib/privat/api";
import { Ico } from "./icons";
import { initials } from "./store";

/** Byggevejledning pieces used across Privat. Buttons come from components/ui.tsx (Button); these are the small extras. */
export const CHIP = "inline-flex items-center gap-2 min-h-[44px] px-3.5 rounded-full border-2 border-ink bg-paper text-ink text-[14px] font-semibold whitespace-nowrap hover:bg-panel";
export const BIG = "min-h-[52px] text-[16px] border-2 border-ink";
export const LINK = "inline-flex items-center min-h-[44px] text-accent text-[15px] font-semibold underline underline-offset-[3px] hover:text-accent-deep self-start";
export const ROW = "w-full flex items-start gap-3 text-left rounded-[14px] border-[1.5px] border-ink bg-paper px-3.5 py-3 text-ink hover:bg-panel";

export const TONE: Record<TaskStatus, string> = {
  awaiting_user: "bg-highlight border-ink text-ink",
  draft: "bg-paper border-ink border-dashed text-ink",
  in_progress: "bg-accent-soft border-accent text-ink",
  planned: "bg-paper border-ink text-ink",
  awaiting_business: "bg-panel border-muted text-ink",
  done: "bg-success-soft border-success text-success",
  declined: "bg-panel border-ink text-ink",
};

export function statusLabel(t: Task, tr: (k: string) => string): string {
  if (t.status === "done" && t.call?.result === "answered") return tr("status.doneConfirmed");
  return tr(`status.${t.status}`);
}

export function StatusBadge({ task }: { task: Task }) {
  const t = useT("privat");
  return <span className={`inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] text-[12px] font-semibold whitespace-nowrap ${TONE[task.status]}`}>{statusLabel(task, t)}</span>;
}

export function Pill({ children, tone = "plain" }: { children: React.ReactNode; tone?: "plain" | "ok" | "soon" | "beta" | "progress" | "highlight" }) {
  const c = { plain: "bg-paper border-ink", ok: "bg-success-soft border-success text-success", soon: "bg-panel border-muted text-ink border-dashed",
    beta: "bg-accent-soft border-accent text-ink", progress: "bg-accent-soft border-accent text-ink", highlight: "bg-highlight border-ink" }[tone];
  return <span className={`inline-flex items-center min-h-6 px-2.5 rounded-full border-[1.5px] text-[12px] font-semibold whitespace-nowrap ${c}`}>{children}</span>;
}

/** «Simuleret»: everything the prototype/fake only pretends to do. */
export function Sim({ label }: { label?: string }) {
  const t = useT("privat");
  return <span className="inline-flex items-center min-h-[22px] px-2 rounded-full border-[1.5px] border-dashed border-ink bg-panel text-[11px] font-semibold tracking-[0.04em] uppercase text-ink whitespace-nowrap">{label ?? t("brand.simulated")}</span>;
}

/** «Eksempel»: example data. */
export function Ex({ label }: { label?: string }) {
  const t = useT("privat");
  return <span className="inline-flex items-center min-h-5 px-[7px] rounded-full bg-panel text-[11px] font-semibold text-muted whitespace-nowrap">{label ?? t("brand.example")}</span>;
}

export function KindLabel({ task }: { task: Task }) {
  const t = useT("privat");
  const k = task.list_type === "wishlist" ? "wishlist" : task.kind;
  return <span className="text-[12px] font-semibold text-muted">{t(`kind.${k}`)}{task.shared && task.my_role && task.my_role !== "owner" ? ` · ${t("groups.shared")}` : ""}</span>;
}

export function Kv({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,118px)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[15px] m-0">
      {rows.map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted font-semibold text-[13px] pt-0.5">{k}</dt><dd className="m-0 [overflow-wrap:anywhere]">{v}</dd></div>))}
    </dl>
  );
}

export function Avatars({ names, size = 32 }: { names: string[]; size?: number }) {
  return (
    <span className="inline-flex items-center">
      {names.slice(0, 5).map((n, i) => (
        <span key={`${n}${i}`} title={n} className={`inline-flex items-center justify-center rounded-full border-2 border-ink font-display font-extrabold text-ink ${i % 2 ? "bg-accent-soft" : "bg-highlight"} ${i ? "-ml-2" : ""}`}
          style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }} aria-hidden>{initials(n)}</span>
      ))}
    </span>
  );
}

export function CheckBox({ done }: { done: boolean }) {
  return (
    <span className={`inline-flex items-center justify-center w-6 h-6 rounded-[7px] border-2 shrink-0 ${done ? "bg-accent border-accent text-white" : "bg-paper border-ink"}`} aria-hidden>
      {done && <Ico name="check" size={16} stroke={3} />}
    </span>
  );
}

export function Eyebrow({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <p className={`eyebrow m-0 ${className}`}>{children}</p>;
}

/** Visually hidden but read by screen readers. */
export const SR = "absolute w-px h-px overflow-hidden [clip:rect(0_0_0_0)] whitespace-nowrap";
