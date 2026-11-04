"use client";
import { useId } from "react";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { Ico } from "@/components/privat/icons";
import { Alert, Button } from "@/components/ui";
import type { Estimate as EstimateT } from "@/lib/funnel/api";

/** One question per screen: a big Outfit title and an optional line of help under it. `eyebrow` carries the ad hook. */
export function Question({ title, help, eyebrow, id = "funnel-q" }: { title: string; help?: string; eyebrow?: string; id?: string }) {
  return (
    <div className="flex flex-col gap-2">
      {eyebrow && <p className="m-0 eyebrow">{eyebrow}</p>}
      <h1 id={id} className="m-0 font-display font-extrabold text-[28px] sm:text-[36px] leading-[1.08] tracking-[-0.6px] text-ink [overflow-wrap:anywhere]">{title}</h1>
      {help && <p className="m-0 text-[16px] leading-normal text-ink-soft">{help}</p>}
    </div>
  );
}

export type Option = { key: string; label: string; hint?: string; icon?: string };

/** Choice chips/cards. Single: radio-like, picking one calls onChange at once (the page usually moves on). Multi:
 *  checkbox-like, toggles. 44 px+ targets, one column on a phone, two from sm when there are many options. */
export function Choice({ options, value, onChange, multi = false, labelledBy = "funnel-q", columns = "auto" }: {
  options: Option[]; value: string | string[] | null | undefined; onChange: (v: string | string[]) => void; multi?: boolean; labelledBy?: string; columns?: "auto" | 1 | 2;
}) {
  const t = useT("site.funnel.common");
  const selected = new Set(Array.isArray(value) ? value : value ? [value] : []);
  const toggle = (k: string) => {
    if (!multi) { onChange(k); return; }
    const n = new Set(selected);
    if (n.has(k)) n.delete(k); else n.add(k);
    onChange(options.filter((o) => n.has(o.key)).map((o) => o.key));
  };
  const cols = columns === 1 ? "grid-cols-1" : columns === 2 ? "grid-cols-1 sm:grid-cols-2" : options.length > 4 ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1";
  return (
    <div role={multi ? "group" : "radiogroup"} aria-labelledby={labelledBy} className={`grid gap-2.5 ${cols}`}>
      <span className="sr-only">{multi ? t("chooseMany") : t("choose")}</span>
      {options.map((o) => {
        const on = selected.has(o.key);
        return (
          <button key={o.key} type="button" role={multi ? "checkbox" : "radio"} aria-checked={on} onClick={() => toggle(o.key)} data-choice={o.key}
            className={`min-h-[56px] w-full flex items-center gap-3 rounded-2xl border-2 border-ink px-4 py-2.5 text-left cursor-pointer transition-colors ${on ? "bg-accent text-on-accent" : "bg-white text-ink hover:bg-panel"}`}>
            {o.icon && <Ico name={o.icon} size={22} className={on ? "text-on-accent" : "text-accent"} />}
            <span className="flex flex-col min-w-0 flex-1">
              <span className="font-semibold text-[16px] leading-tight">{o.label}</span>
              {o.hint && <span className={`text-[13px] leading-snug ${on ? "opacity-90" : "text-muted"}`}>{o.hint}</span>}
            </span>
            <span aria-hidden className={`w-6 h-6 shrink-0 inline-flex items-center justify-center rounded-full border-2 ${on ? "border-on-accent bg-white text-accent" : "border-ink bg-white"}`}>
              {on && <Ico name="check" size={14} stroke={3.2} />}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** The one big action under a question. */
export function NextButton({ children, onClick, disabled, busy, type = "button", form }: { children?: React.ReactNode; onClick?: () => void; disabled?: boolean; busy?: boolean; type?: "button" | "submit"; form?: string }) {
  const t = useT("site.funnel.actions");
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-2">
      <Button type={type} form={form} onClick={onClick} disabled={disabled || busy} className="min-h-[52px] w-full sm:w-auto sm:min-w-[200px] text-[16px] rounded-2xl" data-next>
        {busy ? t("wait") : children ?? t("next")}{!busy && <Ico name="arrow" size={18} stroke={2.8} />}
      </Button>
    </div>
  );
}

/** «ca. 11 opkald om ugen» – the number is an input the person can correct; the source of the estimate is shown.
 *  No fake precision: it is an average for the line of business, and it says so. */
export function Estimate({ value, onChange, source }: { value: number; onChange: (n: number) => void; source: string }) {
  const t = useT("site.funnel.estimate");
  const id = useId();
  return (
    <div className="rounded-2xl border-2 border-ink bg-highlight px-4 py-4 flex flex-col gap-2" data-estimate>
      <label htmlFor={id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[18px] font-semibold text-ink">
        <span>{t("about")}</span>
        <input id={id} type="number" inputMode="numeric" min={0} max={999} value={Number.isFinite(value) ? value : ""}
          onChange={(e) => onChange(Math.max(0, Math.min(999, Math.round(Number(e.target.value) || 0))))}
          className="w-[84px] min-h-[44px] px-2 rounded-xl border-2 border-ink bg-white text-center font-display font-extrabold text-[26px] text-ink focus:outline-none focus:ring-[3px] focus:ring-accent" />
        <span>{t("perWeek")}</span>
      </label>
      <p className="m-0 text-[13px] text-ink-soft">{t("source", { source })} · {t("edit")}</p>
    </div>
  );
}
export type { EstimateT };

/** While the draft loads / when it could not be loaded. */
export function FunnelState({ status, error, onRetry }: { status: "loading" | "error"; error: ApiError | null; onRetry?: () => void }) {
  const t = useT("site.funnel.common");
  if (status === "loading") return <p role="status" className="m-0 text-[15px] text-muted">{t("loading")}</p>;
  return (
    <div className="flex flex-col gap-3">
      <Alert>{error?.message ?? t("errorTitle")}</Alert>
      {onRetry && <Button variant="outline" onClick={onRetry} className="self-start">{t("startOver")}</Button>}
    </div>
  );
}
