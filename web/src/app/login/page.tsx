"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, Button,  ErrorBox, Field, Input, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { safeNext } from "@/lib/safe-next";
import { PasswordField } from "@/components/password-field";
import type { ApiError } from "@/lib/client";

function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const { run, pending, error } = useSubmit(async () => {
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify(form) });
    if (!r.ok) throw (await r.json()) as ApiError;
    const next = params.get("next");
    router.push(safeNext(next));
    router.refresh();
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
      {params.get("expired") && <Alert kind="info">Din session er udløbet. Log ind igen for at fortsætte.</Alert>}
      {params.get("reset") && <Alert kind="ok">Adgangskoden er ændret. Log ind med den nye.</Alert>}
      <ErrorBox error={error} />
      <Field label="E-mail"><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" /></Field>
      <PasswordField label="Adgangskode" value={form.password} onChange={(v) => setForm({ ...form, password: v })} autoComplete="current-password" withRules={false} />
      <Button type="submit" icon="login" disabled={pending} className="w-full h-12 rounded-lg">{pending ? "Logger ind…" : "Log ind"}</Button>
      <p className="flex justify-between font-body-sm text-body-sm text-on-surface-variant">
        <Link className="font-semibold text-primary underline" href="/password/forgot">Glemt adgangskode?</Link>
        <Link className="font-semibold text-primary underline" href="/signup">Opret konto</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthFrame icon="key" title="Log ind" subtitle="Fortsæt til dit arbejdsrum."><Suspense><LoginForm /></Suspense></AuthFrame>
  );
}
