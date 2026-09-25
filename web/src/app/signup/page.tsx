"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button, Card, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

function SignupForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "", display_name: "", signup_intent: params.get("intent") ?? "reception" });
  const { run, pending, error } = useSubmit(async () => {
    await api("/auth/register", { method: "POST", body: JSON.stringify(form) });
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ email: form.email, password: form.password }) });
    if (!r.ok) throw await r.json();
    router.push("/verify-email");
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      <ErrorBox error={error} />
      <Field label="Dit navn" error={fieldError(error, "display_name")}><Input required value={form.display_name} onChange={set("display_name")} autoComplete="name" /></Field>
      <Field label="E-mail" error={fieldError(error, "email")}><Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></Field>
      <Field label="Adgangskode" hint="Mindst 10 tegn" error={fieldError(error, "password")}><Input type="password" required minLength={10} value={form.password} onChange={set("password")} autoComplete="new-password" /></Field>
      <Field label="Jeg vil starte med">
        <select className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm" value={form.signup_intent} onChange={set("signup_intent")}>
          <option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Begge dele</option>
        </select>
      </Field>
      <Button type="submit" disabled={pending} className="w-full">{pending ? "Opretter…" : "Opret konto"}</Button>
      <p className="text-center text-sm text-muted">Har du en konto? <Link className="font-semibold text-primary underline" href="/login">Log ind</Link></p>
    </form>
  );
}

export default function SignupPage() {
  return (
    <main className="mx-auto max-w-md px-4 py-12">
      <h1 className="mb-6 text-2xl font-extrabold text-primary-dark">Opret konto</h1>
      <Card><Suspense><SignupForm /></Suspense></Card>
    </main>
  );
}
