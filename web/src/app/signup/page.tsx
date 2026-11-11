"use client";
import Link from "@/i18n/link";
import { useLocale, useT } from "@/i18n/client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Button,  ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";
import { AuthFrame } from "@/components/auth-frame";
import { safeNext } from "@/lib/safe-next";
import { privatKind, privatNext } from "@/lib/privat-next";
import { PasswordField } from "@/components/password-field";

/** ?next=/privat…, /g/… or /i/… means a Dialogbot Privat sign-up (lib/privat-next.ts): the orange frame, no product
 *  choice (that is an Erhverv question), signup_intent «privat», and `next` goes to the API so the verify link returns
 *  there – the plan's checkout, or the shared list (F-JP-01, F-JP-04, F-JP-05). A shared list or group gets the free
 *  account (no trial, no plan). An invited colleague (?next=/invite/…) joins a company: no product choice either. */
const INTENTS = ["reception", "campaigns", "both"];
const isPrivat = (next: string | null) => privatNext(next) !== null;
const isInvite = (next: string | null) => !!next && next.startsWith("/invite/");

function SignupForm() {
  const params = useSearchParams();
  const router = useRouter();
  const t = useT("auth");
  const locale = useLocale();
  const privat = isPrivat(params.get("next"));
  const free = privat && privatKind(params.get("next")) === "list";
  const invited = isInvite(params.get("next"));
  const [form, setForm] = useState({ email: "", password: "", display_name: "", signup_intent: INTENTS.includes(params.get("intent") ?? "") ? params.get("intent")! : "reception" });
  const { run, pending, error } = useSubmit(async () => {
    const next = params.get("next");
    // The page's language goes with the account, so every account mail is in it (F-JE-07).
    const body = privat ? { ...form, signup_intent: "privat", next: privatNext(next) } : invited ? { ...form, signup_intent: null } : form;
    await api("/auth/register", { method: "POST", body: JSON.stringify({ ...body, interface_language: locale }) });
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ email: form.email, password: form.password }) });
    if (!r.ok) throw await r.json();
    if (next?.startsWith("/ambassador") || invited) { try { localStorage.setItem("db_after_verify", next!); } catch { /* optional */ } }
    // Privat: first the e-mail (the plan's checkout and a shared list need it) – the verify page waits with «Send nyt
    // link», and the mailed link returns to `next`. No 403 on the way (F-JP-01, F-JP-05).
    if (privat) { router.push(`/verify-email?for=privat&next=${encodeURIComponent(privatNext(next)!)}`); return; }
    router.push(safeNext(next, "/verify-email"));
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-3">
      <ErrorBox error={error} />
      <Field label={t("signup.name")} error={fieldError(error, "display_name")}><Input required value={form.display_name} onChange={set("display_name")} autoComplete="name" /></Field>
      <Field label={t("fields.email")} error={fieldError(error, "email")}><Input type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></Field>
      <PasswordField label={t("fields.password")} value={form.password} onChange={(v) => setForm({ ...form, password: v })} error={fieldError(error, "password")} />
      {!privat && !invited && (
        <Field label={t("signup.startWith")}>
          <Select value={form.signup_intent} onChange={set("signup_intent")}>
            <option value="reception">{t("signup.intentReception")}</option><option value="campaigns">{t("signup.intentCampaigns")}</option><option value="both">{t("signup.intentBoth")}</option>
          </Select>
        </Field>
      )}
      <Button type="submit" icon="person_add" disabled={pending} className="w-full h-12 rounded-lg">{pending ? t("signup.submitting") : free ? t("signup.submitFree") : privat ? t("signup.submitPrivat") : t("signup.submit")}</Button>
      <p className="text-center text-body-sm text-ink-soft">{t("signup.haveAccount")} <Link className="text-label-md font-semibold text-muted underline" href={params.get("next") ? `/login?next=${encodeURIComponent(params.get("next")!)}` : "/login"}>{t("signup.login")}</Link></p>
    </form>
  );
}

function SignupScreen() {
  const t = useT("auth");
  const next = useSearchParams().get("next");
  const privat = isPrivat(next);
  const free = privat && privatKind(next) === "list";
  return (
    <AuthFrame icon="person_add" audience={privat ? "privat" : "erhverv"} title={free ? t("signup.freeTitle") : privat ? t("signup.privatTitle") : t("signup.title")} subtitle={free ? t("signup.freeSubtitle") : privat ? t("signup.privatSubtitle") : t("signup.subtitle")}>
      <SignupForm />
    </AuthFrame>
  );
}

export default function SignupPage() {
  return <Suspense><SignupScreen /></Suspense>;
}
