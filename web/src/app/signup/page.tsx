"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button,  ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { PasswordField } from "@/components/password-field";

function SignupForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "", display_name: "", signup_intent: params.get("intent") ?? "reception" });
  const { run, pending, error } = useSubmit(async () => {
    await api("/auth/register", { method: "POST", body: JSON.stringify(form) });
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ email: form.email, password: form.password }) });
    if (!r.ok) throw await r.json();
    const next = params.get("next");
    router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/verify-email");
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
      <ErrorBox error={error} />
      <Field label="Dit navn" error={fieldError(error, "display_name")}><Input required value={form.display_name} onChange={set("display_name")} autoComplete="name" /></Field>
      <Field label="E-mail" error={fieldError(error, "email")}><Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></Field>
      <PasswordField label="Adgangskode" value={form.password} onChange={(v) => setForm({ ...form, password: v })} error={fieldError(error, "password")} />
      <Field label="Jeg vil starte med">
        <Select value={form.signup_intent} onChange={set("signup_intent")}>
          <option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Begge dele</option>
        </Select>
      </Field>
      <Button type="submit" icon="person_add" disabled={pending} className="w-full h-12 rounded-lg">{pending ? "Opretter…" : "Opret konto"}</Button>
      <p className="text-center font-body-sm text-body-sm text-on-surface-variant">Har du en konto? <Link className="text-label-md font-semibold text-secondary underline" href="/login">Log ind</Link></p>
    </form>
  );
}

export default function SignupPage() {
  return (
    <AuthFrame code="A01" icon="person_add" title="Opret konto" subtitle="Dit produktvalg følger med til opsætningen, så planen passer til det, du vil bruge Dialogbot til."><Suspense><SignupForm /></Suspense></AuthFrame>
  );
}
