"use client";
import Link from "@/i18n/link";
import { useT } from "@/i18n/client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button,  ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { safeNext } from "@/lib/safe-next";
import { PasswordField } from "@/components/password-field";

/** ?next=/privat… means a Dialogbot Privat sign-up: the orange frame, no product choice (that is an Erhverv question)
 *  and the login link keeps `next`, so a plan picked on the landing page goes straight on to the payment after. */
const isPrivat = (next: string | null) => !!next && next.startsWith("/privat");

function SignupForm() {
  const params = useSearchParams();
  const router = useRouter();
  const t = useT("auth");
  const privat = isPrivat(params.get("next"));
  const [form, setForm] = useState({ email: "", password: "", display_name: "", signup_intent: params.get("intent") ?? "reception" });
  const { run, pending, error } = useSubmit(async () => {
    await api("/auth/register", { method: "POST", body: JSON.stringify(privat ? { ...form, signup_intent: null } : form) });
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ email: form.email, password: form.password }) });
    if (!r.ok) throw await r.json();
    const next = params.get("next");
    if (next?.startsWith("/ambassador")) { try { localStorage.setItem("db_after_verify", next); } catch { /* optional */ } }
    router.push(safeNext(next, "/verify-email"));
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
      <ErrorBox error={error} />
      <Field label={t("signup.name")} error={fieldError(error, "display_name")}><Input required value={form.display_name} onChange={set("display_name")} autoComplete="name" /></Field>
      <Field label={t("fields.email")} error={fieldError(error, "email")}><Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></Field>
      <PasswordField label={t("fields.password")} value={form.password} onChange={(v) => setForm({ ...form, password: v })} error={fieldError(error, "password")} />
      {!privat && (
        <Field label={t("signup.startWith")}>
          <Select value={form.signup_intent} onChange={set("signup_intent")}>
            <option value="reception">{t("signup.intentReception")}</option><option value="campaigns">{t("signup.intentCampaigns")}</option><option value="both">{t("signup.intentBoth")}</option>
          </Select>
        </Field>
      )}
      <Button type="submit" icon="person_add" disabled={pending} className="w-full h-12 rounded-lg">{pending ? t("signup.submitting") : privat ? t("signup.submitPrivat") : t("signup.submit")}</Button>
      <p className="text-center text-body-sm text-ink-soft">{t("signup.haveAccount")} <Link className="text-label-md font-semibold text-muted underline" href={params.get("next") ? `/login?next=${encodeURIComponent(params.get("next")!)}` : "/login"}>{t("signup.login")}</Link></p>
    </form>
  );
}

function SignupScreen() {
  const t = useT("auth");
  const privat = isPrivat(useSearchParams().get("next"));
  return (
    <AuthFrame icon="person_add" audience={privat ? "privat" : "erhverv"} title={privat ? t("signup.privatTitle") : t("signup.title")} subtitle={privat ? t("signup.privatSubtitle") : t("signup.subtitle")}>
      <SignupForm />
    </AuthFrame>
  );
}

export default function SignupPage() {
  return <Suspense><SignupScreen /></Suspense>;
}
