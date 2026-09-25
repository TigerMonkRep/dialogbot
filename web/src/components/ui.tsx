"use client";
import Link from "next/link";
import { useState } from "react";
import type { ApiError } from "@/lib/client";

export function Button({ variant = "primary", className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  const base = "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed";
  const v = {
    primary: "bg-primary text-white hover:bg-primary-dark",
    secondary: "bg-accent text-primary-dark hover:brightness-95",
    ghost: "text-primary hover:bg-white/60",
    danger: "bg-danger text-white hover:brightness-90",
  }[variant];
  return <button className={`${base} ${v} ${className}`} {...p} />;
}

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-semibold text-primary-dark">{label}</span>
      {children}
      {hint && !error && <span className="block text-xs text-muted">{hint}</span>}
      {error && <span role="alert" className="block text-xs font-medium text-danger">{error}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-muted/70 focus:border-primary";

export function Input(p: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={inputCls} {...p} />;
}

export function Textarea(p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${inputCls} min-h-24`} {...p} />;
}

export function Card({ title, children, actions, className = "" }: { title?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-line bg-white/90 p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-bold text-primary-dark">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Alert({ kind = "error", children }: { kind?: "error" | "ok" | "info"; children: React.ReactNode }) {
  const c = { error: "border-danger/40 bg-red-50 text-danger", ok: "border-ok/40 bg-green-50 text-ok", info: "border-line bg-white text-primary-dark" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded-xl border px-4 py-3 text-sm ${c}`}>{children}</div>;
}

export function ErrorBox({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <Alert>
      {error.message}
      {error.request_id && <span className="mt-1 block text-xs opacity-70">Reference: {error.request_id}</span>}
    </Alert>
  );
}

export function Badge({ status }: { status: string }) {
  const map: Record<string, string> = {
    complete: "bg-green-100 text-ok", passed: "bg-green-100 text-ok", approved: "bg-green-100 text-ok",
    in_progress: "bg-accent text-primary-dark", in_review: "bg-accent text-primary-dark", stale: "bg-yellow-100 text-yellow-900",
    not_started: "bg-white text-muted border border-line", untested: "bg-white text-muted border border-line", draft: "bg-white text-muted border border-line",
    blocked: "bg-orange-100 text-orange-900", not_available: "bg-gray-200 text-gray-700", skipped: "bg-gray-100 text-muted",
    failed: "bg-red-100 text-danger", rejected: "bg-red-100 text-danger", superseded: "bg-gray-100 text-muted",
  };
  const label: Record<string, string> = {
    complete: "Gennemført", in_progress: "I gang", not_started: "Ikke startet", blocked: "Blokeret", not_available: "Ikke tilgængelig",
    skipped: "Sprunget over", passed: "Bestået", failed: "Fejlet", stale: "Forældet", untested: "Ikke testet",
    draft: "Kladde", in_review: "Til gennemgang", approved: "Godkendt", superseded: "Erstattet", rejected: "Afvist", pending: "Afventer",
  };
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[status] ?? "bg-white text-muted"}`}>{label[status] ?? status}</span>;
}

/** Simple submit helper: tracks pending/error for a form action. */
export function useSubmit<T>(fn: () => Promise<T>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = async () => {
    setPending(true); setError(null);
    try { return await fn(); } catch (e) { setError(e as ApiError); return undefined; } finally { setPending(false); }
  };
  return { run, pending, error, setError };
}

export function Steps({ current }: { current: string }) {
  const steps = [
    ["/onboarding/workspace", "Arbejdsrum"], ["/onboarding/business", "Virksomhed"], ["/onboarding/goals", "Mål"],
    ["/onboarding/languages", "Sprog"], ["/app/knowledge", "Viden"], ["/app/setup", "Plan"],
  ];
  return (
    <nav aria-label="Opsætningstrin" className="mb-6 flex flex-wrap gap-2 text-xs">
      {steps.map(([href, label], i) => (
        <Link key={href} href={href} className={`rounded-full px-3 py-1 font-semibold ${href === current ? "bg-primary text-white" : "bg-white text-primary-dark border border-line"}`}>
          {i + 1}. {label}
        </Link>
      ))}
    </nav>
  );
}
