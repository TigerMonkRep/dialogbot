"use client";
import { useState } from "react";
import type { ApiError } from "@/lib/client";

/* Byggevejledning design system v2 (docs/brand.md). Flat colours, 2 px ink outlines,
   one action colour (accent / Klods-blå), one "you are here" colour (highlight / Trin-gul). */

/** Logo mark: blue rounded square (radius 28 %) with a white speech bubble (docs/brand.md). */
export function LogoMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center justify-center bg-accent shrink-0 ${className}`} style={{ width: size, height: size, borderRadius: Math.round(size * 0.28) }} aria-hidden>
      <svg width={Math.round(size * 0.56)} height={Math.round(size * 0.56)} viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4z" /></svg>
    </span>
  );
}

/** Material Symbol icon */
export function Icon({ name, size = 20, className = "", filled = false }: { name: string; size?: number; className?: string; filled?: boolean }) {
  return <span aria-hidden className={`material-symbols-outlined ${filled ? "filled" : ""} ${className}`} style={{ fontSize: size }}>{name}</span>;
}

type BtnVariant = "primary" | "secondary" | "tonal" | "ghost" | "danger" | "outline";
export function Button({ variant = "primary", icon, className = "", children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; icon?: string }) {
  const base = "inline-flex items-center justify-center gap-2 rounded-xl min-h-[44px] px-4 py-2 font-body text-[15px] font-semibold leading-tight transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const v: Record<BtnVariant, string> = {
    primary: "bg-accent text-white hover:bg-accent-deep",
    secondary: "bg-highlight text-ink hover:bg-highlight-deep",
    tonal: "bg-panel text-ink border-2 border-transparent hover:bg-panel-deep",
    ghost: "text-ink hover:bg-panel",
    outline: "bg-paper text-ink border-2 border-ink hover:bg-panel",
    danger: "bg-danger text-white hover:brightness-95",
  };
  return <button className={`${base} ${v[variant]} ${className}`} {...p}>{icon && <Icon name={icon} size={18} />}{children}</button>;
}

/** Eyebrow label: Inter 600 · 12 px · uppercase · +0.12 em · muted. */
export function SectionLabel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`eyebrow block ${className}`}>{children}</span>;
}

/** Standard card: paper, 2 px ink outline, 20 px radius, no shadow. `raised` adds the single block shadow (one per section). */
export function Card({ title, label, subtitle, children, actions, className = "", raised = false }: { title?: string; label?: string; subtitle?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string; raised?: boolean }) {
  return (
    <section className={`rounded-2xl bg-paper border-2 border-ink p-6 space-y-4 ${raised ? "shadow-block" : ""} ${className}`}>
      {(title || label || actions) && (
        <header className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {label && <SectionLabel>{label}</SectionLabel>}
            {title && <h3 className="font-display text-headline-sm text-ink mt-1">{title}</h3>}
            {subtitle && <p className="text-body-sm text-ink-soft mt-1">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export const inputCls = "w-full min-h-[46px] px-3.5 py-2 rounded-xl bg-paper border-2 border-ink text-ink font-body text-[15px] placeholder:text-muted focus:outline-none focus:ring-[3px] focus:ring-accent focus:ring-offset-2 disabled:opacity-60 disabled:border-line";

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-[13px] font-semibold text-ink">{label}</span>
      {children}
      {hint && !error && <span className="block text-body-sm text-muted">{hint}</span>}
      {error && <span role="alert" className="block text-label-md text-danger">{error}</span>}
    </label>
  );
}
export function Input({ className = "", ...p }: React.InputHTMLAttributes<HTMLInputElement>) { return <input className={`${inputCls} ${className}`} {...p} />; }
export function Textarea({ className = "", ...p }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className={`${inputCls} min-h-24 py-3 ${className}`} {...p} />; }
export function Select({ className = "", ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) { return <select className={`${inputCls} ${className}`} {...p} />; }

export function Alert({ kind = "error", children, icon }: { kind?: "error" | "ok" | "info" | "warn"; children: React.ReactNode; icon?: string }) {
  const c = {
    error: "bg-danger-soft text-on-error-container border-danger", ok: "bg-success-soft text-success border-success",
    info: "bg-panel text-ink border-ink", warn: "bg-highlight text-ink border-ink",
  }[kind];
  const ic = icon ?? { error: "error", ok: "check_circle", info: "info", warn: "warning" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`flex items-start gap-2.5 rounded-xl border-[1.5px] p-3.5 text-body-sm ${c}`}><Icon name={ic} size={20} className="shrink-0" /><div className="min-w-0">{children}</div></div>;
}

export function ErrorBox({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <Alert>{error.message}{error.request_id && <span className="mt-1 block text-label-sm opacity-70">Reference: {error.request_id}</span>}</Alert>;
}

/* Status pills. ok = soft green (only for things that really work), progress = accent-soft,
   error = danger-soft, neutral = panel with 1.5 px ink outline, pending = Trin-gul. */
const PILL = {
  ok: "bg-success-soft text-success border-success-soft",
  progress: "bg-accent-soft text-accent-deep border-accent-soft",
  pending: "bg-highlight text-ink border-highlight",
  error: "bg-danger-soft text-on-error-container border-danger-soft",
  failed: "bg-danger text-white border-danger",
  neutral: "bg-panel text-ink border-ink",
  off: "bg-paper text-muted border-ink border-dashed",
} as const;
type Pill = keyof typeof PILL;
const STATUS: Record<string, [string, Pill]> = {
  complete: ["Gennemført", "ok"], passed: ["Bestået", "ok"], approved: ["Godkendt", "ok"], published: ["Gået ud", "ok"], accepted: ["Accepteret", "ok"],
  in_progress: ["I gang", "progress"], in_review: ["Til gennemgang", "progress"], scheduled: ["Planlagt", "progress"], publishing: ["Poster nu", "progress"],
  pending: ["Afventer", "pending"],
  stale: ["Forældet", "error"], rejected: ["Afvist", "error"], blocked: ["Blokeret", "error"], expired: ["Udløbet", "error"],
  failed: ["Fejlet", "failed"],
  not_available: ["Ikke tilgængelig", "off"], not_started: ["Ikke startet", "off"], untested: ["Ikke testet", "off"], skipped: ["Sprunget over", "off"],
  draft: ["Kladde", "neutral"], superseded: ["Erstattet", "neutral"], cancelled: ["Annulleret", "neutral"], revoked: ["Tilbagekaldt", "neutral"],
};
export function Badge({ status }: { status: string }) {
  const [label, tone] = STATUS[status] ?? [status, "neutral" as Pill];
  return <span className={`inline-flex items-center rounded-full border-[1.5px] px-2.5 py-0.5 text-[12px] font-semibold uppercase tracking-[0.06em] whitespace-nowrap ${PILL[tone]}`}>{label}</span>;
}
export function Tag({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "secondary" | "tertiary" }) {
  const c = { neutral: "bg-panel text-ink border-[1.5px] border-ink", secondary: "bg-highlight text-ink font-semibold", tertiary: "bg-accent-soft text-accent-deep font-semibold" }[tone];
  return <span className={`inline-flex items-center rounded-lg px-2 py-0.5 text-label-sm tracking-normal ${c}`}>{children}</span>;
}

export function useSubmit<A extends unknown[], T>(fn: (...args: A) => Promise<T>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = async (...args: A) => { setPending(true); setError(null); try { return await fn(...args); } catch (e) { setError(e as ApiError); return undefined; } finally { setPending(false); } };
  return { run, pending, error, setError };
}

export function Breadcrumb({ items }: { items: [string, string?][] }) {
  return (
    <div className="flex items-center gap-1 text-label-md text-muted">
      {items.map(([label, href], i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <Icon name="chevron_right" size={14} />}
          {href ? <a href={href} className={i === items.length - 1 ? "text-ink font-semibold" : "hover:text-ink"}>{label}</a> : <span className={i === items.length - 1 ? "text-ink font-semibold" : ""}>{label}</span>}
        </span>
      ))}
    </div>
  );
}

/** Progress ring: ink track, accent progress, Outfit numeral. */
export function ProgressRing({ percent }: { percent: number }) {
  return (
    <div className="relative w-14 h-14 flex items-center justify-center">
      <svg className="w-14 h-14 -rotate-90" viewBox="0 0 36 36">
        <path className="text-line" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3.5" />
        <path className="text-accent" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray={`${percent}, 100`} strokeLinecap="butt" strokeWidth="3.5" />
      </svg>
      <span className="absolute font-display text-[15px] font-extrabold text-ink">{percent}%</span>
    </div>
  );
}
