"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
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
  const t = useT("auth");
  const [form, setForm] = useState({ email: "", password: "" });
  const { run, pending, error } = useSubmit(async () => {
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify(form) });
    if (!r.ok) throw (await r.json()) as ApiError;
    const next = params.get("next");
    router.push(safeNext(next));
    router.refresh();
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
      {params.get("expired") && <Alert kind="info">{t("login.expired")}</Alert>}
      {params.get("reset") && <Alert kind="ok">{t("login.reset")}</Alert>}
      <ErrorBox error={error} />
      <Field label={t("fields.email")}><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" /></Field>
      <PasswordField label={t("fields.password")} value={form.password} onChange={(v) => setForm({ ...form, password: v })} autoComplete="current-password" withRules={false} />
      <Button type="submit" icon="login" disabled={pending} className="w-full h-12 rounded-lg">{pending ? t("login.submitting") : t("login.submit")}</Button>
      <p className="flex justify-between text-body-sm text-ink-soft">
        <Link className="font-semibold text-ink underline" href="/password/forgot">{t("login.forgot")}</Link>
        <Link className="font-semibold text-ink underline" href="/signup">{t("login.signup")}</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  const t = useT("auth");
  return (
    <AuthFrame icon="key" title={t("login.title")} subtitle={t("login.subtitle")}><Suspense><LoginForm /></Suspense></AuthFrame>
  );
}
