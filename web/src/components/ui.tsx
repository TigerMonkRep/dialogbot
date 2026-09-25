"use client";
import { useState } from "react";
import type { ApiError } from "@/lib/client";

/** Material Symbol icon */
export function Icon({ name, size = 20, className = "", filled = false }: { name: string; size?: number; className?: string; filled?: boolean }) {
  return <span aria-hidden className={`material-symbols-outlined ${filled ? "filled" : ""} ${className}`} style={{ fontSize: size }}>{name}</span>;
}

type BtnVariant = "primary" | "secondary" | "tonal" | "ghost" | "danger" | "outline";
export function Button({ variant = "primary", icon, className = "", children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; icon?: string }) {
  const base = "inline-flex items-center justify-center gap-space-xs rounded-xl px-space-lg py-2.5 text-label-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm";
  const v: Record<BtnVariant, string> = {
    primary: "bg-primary text-on-primary hover:bg-primary-container",
    secondary: "bg-secondary-fixed text-on-secondary-fixed hover:brightness-105 font-bold",
    tonal: "bg-surface-container-low text-primary hover:bg-surface-container shadow-none",
    ghost: "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface shadow-none",
    outline: "bg-surface-container-lowest text-primary border border-outline-variant hover:bg-surface-container-low shadow-none",
    danger: "bg-error text-on-error hover:brightness-95",
  };
  return <button className={`${base} ${v[variant]} ${className}`} {...p}>{icon && <Icon name={icon} size={18} />}{children}</button>;
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return <span className="text-secondary text-label-sm font-bold uppercase tracking-wider">{children}</span>;
}

export function Card({ title, label, subtitle, children, actions, className = "" }: { title?: string; label?: string; subtitle?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg ${className}`}>
      {(title || label || actions) && (
        <header className="flex items-start justify-between gap-space-md">
          <div>
            {label && <SectionLabel>{label}</SectionLabel>}
            {title && <h3 className="font-display text-headline-sm text-primary font-bold mt-1">{title}</h3>}
            {subtitle && <p className="text-body-sm text-on-surface-variant">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export const inputCls = "w-full px-3 py-2 rounded-lg bg-surface text-on-surface font-body-md text-body-md placeholder:text-on-surface-variant/60 focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary shadow-inner disabled:opacity-60";

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block font-label-md text-label-md text-on-surface font-semibold">{label}</span>
      {children}
      {hint && !error && <span className="block font-body-sm text-body-sm text-on-surface-variant">{hint}</span>}
      {error && <span role="alert" className="block text-label-md text-error">{error}</span>}
    </label>
  );
}
export function Input({ className = "", ...p }: React.InputHTMLAttributes<HTMLInputElement>) { return <input className={`${inputCls} ${className}`} {...p} />; }
export function Textarea({ className = "", ...p }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className={`${inputCls} min-h-24 ${className}`} {...p} />; }
export function Select({ className = "", ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) { return <select className={`${inputCls} ${className}`} {...p} />; }

export function Alert({ kind = "error", children, icon }: { kind?: "error" | "ok" | "info" | "warn"; children: React.ReactNode; icon?: string }) {
  const c = {
    error: "bg-error-container/40 text-on-error-container", ok: "bg-secondary-container text-on-secondary-container",
    info: "bg-surface-container-high text-on-surface", warn: "bg-tertiary-fixed text-on-tertiary-fixed",
  }[kind];
  const ic = icon ?? { error: "error", ok: "check_circle", info: "info", warn: "warning" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`flex items-start gap-space-sm rounded-lg p-space-md text-body-sm ${c}`}><Icon name={ic} size={20} className="shrink-0" /><div>{children}</div></div>;
}

export function ErrorBox({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return <Alert>{error.message}{error.request_id && <span className="mt-1 block text-label-sm opacity-70">Reference: {error.request_id}</span>}</Alert>;
}

const STATUS: Record<string, [string, string]> = {
  complete: ["Gennemført", "bg-secondary-container text-on-secondary-container"], passed: ["Bestået", "bg-secondary-container text-on-secondary-container"], approved: ["Godkendt", "bg-secondary-container text-on-secondary-container"],
  in_progress: ["I gang", "bg-tertiary-fixed text-on-tertiary-fixed"], in_review: ["Til gennemgang", "bg-tertiary-fixed text-on-tertiary-fixed"], pending: ["Afventer", "bg-tertiary-fixed text-on-tertiary-fixed"],
  stale: ["Forældet", "bg-error-container text-on-error-container"], failed: ["Fejlet", "bg-error text-on-error"], rejected: ["Afvist", "bg-error-container text-on-error-container"],
  blocked: ["Blokeret", "bg-error-container/60 text-on-error-container"], not_available: ["Ikke tilgængelig", "bg-surface-container-highest text-on-surface-variant"],
  not_started: ["Ikke startet", "bg-surface-container-high text-on-surface-variant"], untested: ["Ikke testet", "bg-surface-container-high text-on-surface-variant"],
  draft: ["Kladde", "bg-surface-container-high text-on-surface"], superseded: ["Erstattet", "bg-surface-container-highest text-on-surface-variant"], skipped: ["Sprunget over", "bg-surface-container-highest text-on-surface-variant"],
  revoked: ["Tilbagekaldt", "bg-surface-container-highest text-on-surface-variant"], expired: ["Udløbet", "bg-error-container text-on-error-container"], accepted: ["Accepteret", "bg-secondary-container text-on-secondary-container"],
};
export function Badge({ status }: { status: string }) {
  const [label, cls] = STATUS[status] ?? [status, "bg-surface-container-high text-on-surface"];
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-label-sm font-semibold ${cls}`}>{label}</span>;
}
export function Tag({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "secondary" | "tertiary" }) {
  const c = { neutral: "bg-surface-container-highest text-on-surface", secondary: "bg-secondary-fixed text-on-secondary-fixed font-semibold", tertiary: "bg-tertiary-fixed text-on-tertiary-fixed font-semibold" }[tone];
  return <span className={`rounded px-1.5 py-0.5 text-label-sm ${c}`}>{children}</span>;
}

export function useSubmit<A extends unknown[], T>(fn: (...args: A) => Promise<T>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = async (...args: A) => { setPending(true); setError(null); try { return await fn(...args); } catch (e) { setError(e as ApiError); return undefined; } finally { setPending(false); } };
  return { run, pending, error, setError };
}

export function Breadcrumb({ items }: { items: [string, string?][] }) {
  return (
    <div className="flex items-center gap-space-xs text-label-md text-on-surface-variant">
      {items.map(([label, href], i) => (
        <span key={i} className="flex items-center gap-space-xs">
          {i > 0 && <Icon name="chevron_right" size={14} />}
          {href ? <a href={href} className={i === items.length - 1 ? "text-primary font-semibold" : "hover:text-primary"}>{label}</a> : <span className={i === items.length - 1 ? "text-primary font-semibold" : ""}>{label}</span>}
        </span>
      ))}
    </div>
  );
}

/** Progress ring from the G01 banner */
export function ProgressRing({ percent }: { percent: number }) {
  return (
    <div className="relative w-14 h-14 flex items-center justify-center">
      <svg className="w-14 h-14 -rotate-90" viewBox="0 0 36 36">
        <path className="text-surface-container-highest" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeWidth="3.5" />
        <path className="text-secondary" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" strokeDasharray={`${percent}, 100`} strokeLinecap="round" strokeWidth="3.5" />
      </svg>
      <span className="absolute font-display text-headline-sm font-bold text-primary">{percent}%</span>
    </div>
  );
}
