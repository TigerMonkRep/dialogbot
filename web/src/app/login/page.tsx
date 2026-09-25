"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, Button,  ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import type { ApiError } from "@/lib/client";

function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const { run, pending, error } = useSubmit(async () => {
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify(form) });
    if (!r.ok) throw (await r.json()) as ApiError;
    const next = params.get("next");
    router.push(next && next.startsWith("/") ? next : "/app");
    router.refresh();
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      {params.get("expired") && <Alert kind="info">Din session er udløbet. Log ind igen for at fortsætte.</Alert>}
      {params.get("reset") && <Alert kind="ok">Adgangskoden er ændret. Log ind med den nye.</Alert>}
      <ErrorBox error={error} />
      <Field label="E-mail"><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" /></Field>
      <Field label="Adgangskode"><Input type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="current-password" /></Field>
      <Button type="submit" disabled={pending} className="w-full">{pending ? "Logger ind…" : "Log ind"}</Button>
      <p className="flex justify-between text-body-sm text-on-surface-variant">
        <Link className="font-semibold text-primary underline" href="/password/forgot">Glemt adgangskode?</Link>
        <Link className="font-semibold text-primary underline" href="/signup">Opret konto</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthFrame code="A02" title="Log ind" subtitle="Fortsæt til dit arbejdsrum."><Suspense><LoginForm /></Suspense></AuthFrame>
  );
}
